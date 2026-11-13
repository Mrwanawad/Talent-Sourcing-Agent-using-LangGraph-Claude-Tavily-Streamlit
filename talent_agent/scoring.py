"""Fit scoring: bge-m3 similarity + LLM-as-judge rubric with evidence quotes + calibration."""

from __future__ import annotations

import logging
import pickle
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from talent_agent.config import get_settings
from talent_agent.llm import LLM
from talent_agent.models import CriterionScore, Profile, ScoredCandidate, SearchCriteria
from talent_agent.observability import observe

log = logging.getLogger(__name__)

CALIBRATOR_PATH = Path("models/calibrator.pkl")

JUDGE_SYSTEM = """You are a strict, fair recruiter scoring candidates against a rubric. Each candidate is marked [index].
For EACH candidate and EACH rubric criterion (use the exact criterion name) give a score 0.0-1.0 and an evidence
quote copied VERBATIM from that candidate's text. If there is no evidence, score 0 and evidence "".
Never infer from name, gender, age, religion, nationality or photos. Judge only professional evidence."""


class JudgeOutput(BaseModel):
    index: int
    criteria: list[CriterionScore]


class JudgeBatch(BaseModel):
    candidates: list[JudgeOutput]


# ---------- embeddings ----------


@lru_cache(maxsize=1)
def _encoder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_model)


def brief_text(c: SearchCriteria) -> str:
    return (
        f"{c.title} ({', '.join(c.title_synonyms_en)}) in {c.location}. Seniority {c.seniority.value}. "
        f"Skills: {', '.join(c.skills)}. Companies: {', '.join(c.target_companies)}."
    )


def profile_text(p: Profile) -> str:
    return (
        f"{p.current_title} at {p.company}, {p.city}. {p.summary} Skills: {', '.join(p.skills)}. Achievements: {'; '.join(p.achievements)}"
    )


def embedding_similarity(c: SearchCriteria, profiles: list[Profile]) -> list[float]:
    if not profiles:
        return []
    if get_settings().use_embeddings:
        try:
            enc = _encoder()
            vecs = enc.encode([brief_text(c)] + [profile_text(p) for p in profiles], normalize_embeddings=True)
            sims = vecs[1:] @ vecs[0]
            return [float(max(0.0, s)) for s in sims]
        except Exception as exc:
            log.warning("embeddings unavailable, using token overlap: %s", exc)
    return [_overlap(brief_text(c), profile_text(p)) for p in profiles]


def _overlap(a: str, b: str) -> float:
    ta, tb = set(a.lower().split()), set(b.lower().split())
    return len(ta & tb) / (len(ta) or 1)


# ---------- LLM judge ----------


def judge_all(c: SearchCriteria, profiles: list[Profile], llm: LLM) -> list[list[CriterionScore]]:
    """Several candidates per LLM call; keyword judge for any candidate the LLM misses."""
    got: dict[int, list[CriterionScore]] = {}
    if llm.enabled and profiles:
        from talent_agent.extractor import batched

        texts = [p.raw_text[:3000] for p in profiles]
        batches = batched(list(range(len(profiles))), [len(t) + 500 for t in texts], max_items=6, max_chars=14000)
        with ThreadPoolExecutor(max_workers=3) as pool:
            for result in pool.map(lambda b: _judge_batch(c, b, profiles, texts, llm), batches):
                got.update(result)
    out = []
    for i, p in enumerate(profiles):
        rules = _keyword_judge(c, p)
        out.append(_merge_hard_filters(_ground(got[i], p), rules) if i in got else rules)
    return out


def _merge_hard_filters(llm_scores: list[CriterionScore], rules: list[CriterionScore]) -> list[CriterionScore]:
    """Role and location: keep the better of LLM and rule score (snippets often hide what the URL/title show)."""
    by_name = {s.criterion.lower(): s for s in llm_scores}
    for r in rules:
        name = r.criterion.lower()
        if not any(k in name for k in ("role", "title", "location")):
            continue
        cur = by_name.get(name)
        if cur is None:
            llm_scores.append(r)
        elif r.score > cur.score:
            cur.score, cur.evidence = r.score, r.evidence
    return llm_scores


def _judge_batch(c: SearchCriteria, idx: list[int], profiles: list[Profile], texts: list[str], llm: LLM) -> dict[int, list[CriterionScore]]:
    rubric = "\n".join(f"- {r.name} (weight {r.weight}{', MUST' if r.must_have else ''}): {r.description}" for r in c.rubric)
    cands = "\n\n".join(f"[{i}] PROFILE: {profiles[i].model_dump_json(exclude={'raw_text'})}\nPAGE TEXT: {texts[i]}" for i in idx)
    try:
        out = llm.structured(JUDGE_SYSTEM, f"RUBRIC:\n{rubric}\n\nCANDIDATES:\n{cands}", JudgeBatch, max_tokens=700 * len(idx))
        return {j.index: j.criteria for j in out.candidates if j.index in idx}
    except Exception as exc:
        log.warning("judge batch failed (%d candidates): %s", len(idx), exc)
        return {}


def _ground(scores: list[CriterionScore], p: Profile) -> list[CriterionScore]:
    """Evidence must appear in the source text; otherwise halve the score (hallucination guard)."""
    corpus = (p.raw_text + " " + profile_text(p)).lower()
    for s in scores:
        if s.evidence and s.evidence.lower()[:60] not in corpus:
            s.score = round(s.score * 0.5, 3)
            s.evidence = f"[unverified] {s.evidence}"
    return scores


def _keyword_judge(c: SearchCriteria, p: Profile) -> list[CriterionScore]:
    """Offline fallback. Role/location/seniority use the structured criteria; other criteria match listed terms."""
    text = (profile_text(p) + " " + p.raw_text).lower()
    out = []
    for r in c.rubric:
        name = r.name.lower()
        if "role" in name or "title" in name:
            score, found = _best_title(p.current_title or text, [c.title, *c.title_synonyms_en, *c.title_synonyms_ar])
        elif "location" in name:
            score, found = _location(c, p, text)
        elif "senior" in name or "track record" in name:
            found = p.achievements[:1] + ([f"{p.years_experience:g} years"] if p.years_experience else [])
            years = min(1.0, p.years_experience / c.min_years) if p.years_experience and c.min_years else 0.5 * bool(p.years_experience)
            score = 0.5 * years + 0.5 * bool(p.achievements)
        else:
            terms = [t.strip().lower() for t in r.description.replace(";", ",").split(",") if t.strip()]
            found = [t for t in terms if t in text or _token_hit(t, text)]
            score = len(found) / len(terms) if terms else 0.0
        out.append(CriterionScore(criterion=r.name, score=round(score, 3), evidence=", ".join(found)))
    return out


# LinkedIn country subdomain (eg.linkedin.com) as a weak location signal when the city isn't listed
COUNTRY_CODES = {
    "egypt": "eg", "cairo": "eg", "giza": "eg", "alexandria": "eg",
    "uae": "ae", "dubai": "ae", "abu dhabi": "ae", "saudi": "sa", "ksa": "sa", "riyadh": "sa", "jeddah": "sa",
}  # fmt: skip


def _location(c: SearchCriteria, p: Profile, text: str) -> tuple[float, list[str]]:
    found = [a for a in [c.location.split(",")[0], *c.location_aliases] if a.lower() in text]
    if found:
        return 1.0, found
    target = next((cc for place, cc in COUNTRY_CODES.items() if place in c.location.lower()), None)
    m = re.match(r"https?://([a-z]{2})\.linkedin\.com", p.profile_url)
    if target and m and m.group(1) == target:
        return 0.6, [f"{m.group(1)}.linkedin.com"]
    return 0.0, []


def _best_title(have: str, wanted: list[str]) -> tuple[float, list[str]]:
    from rapidfuzz import fuzz

    best = max(((fuzz.token_set_ratio(have.lower(), w.lower()) / 100, w) for w in wanted if w), default=(0.0, ""))
    score = 1.0 if best[0] >= 0.85 else round(best[0], 3) if best[0] >= 0.5 else 0.0
    return score, [have] if score else []


def _token_hit(term: str, text: str) -> bool:
    """All words of a multi-word skill appear (e.g. 'real estate sales' in '... sales in real estate')."""
    words = [w for w in term.split() if len(w) > 2]
    return len(words) > 1 and all(w in text for w in words)


def weighted(c: SearchCriteria, scores: list[CriterionScore]) -> float:
    by_name = {s.criterion.lower(): s.score for s in scores}
    total = sum(r.weight * by_name.get(r.name.lower(), 0.0) for r in c.rubric)
    if any(r.must_have and by_name.get(r.name.lower(), 0.0) < 0.3 for r in c.rubric):
        total *= 0.5  # failed must-have halves the score, independent of rubric order
    return round(total, 3)


# ---------- calibration ----------


def combine(emb: float, judge_score: float) -> float:
    w = get_settings().embedding_weight
    raw = w * emb + (1 - w) * judge_score
    if CALIBRATOR_PATH.exists():
        try:
            model = pickle.loads(CALIBRATOR_PATH.read_bytes())
            return float(model.predict_proba(np.array([[emb, judge_score]]))[0, 1])
        except Exception as exc:
            log.warning("calibrator load failed: %s", exc)
    return round(raw, 3)


def fit_calibrator(features: list[tuple[float, float]], accepted: list[int]) -> None:
    """Fit on manager decisions (1=accepted). Run from evals/calibrate.py."""
    from sklearn.linear_model import LogisticRegression

    model = LogisticRegression().fit(np.array(features), np.array(accepted))
    CALIBRATOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    CALIBRATOR_PATH.write_bytes(pickle.dumps(model))


@observe(name="score")
def score_all(c: SearchCriteria, profiles: list[Profile], llm: LLM | None = None) -> list[ScoredCandidate]:
    llm = llm or LLM()
    sims = embedding_similarity(c, profiles)
    judged = judge_all(c, profiles, llm)
    out = []
    for p, sim, crit in zip(profiles, sims, judged, strict=True):
        js = weighted(c, crit)
        out.append(
            ScoredCandidate(profile=p, embedding_similarity=round(sim, 3), judge_score=js, fit_score=combine(sim, js), criteria=crit)
        )
    return sorted(out, key=lambda x: x.fit_score, reverse=True)
