"""Offline tests: no API keys, no network. LLM stages fall back to rules."""

from __future__ import annotations

import pandas as pd
import pytest

from talent_agent import dedup, export, extractor, query_planner, scoring
from talent_agent.brief_parser import parse_brief
from talent_agent.models import CriterionScore, HiringBrief, Profile, ScoredCandidate, SearchHit, SearchReport


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "TAVILY_API_KEY", "EXA_API_KEY", "LANGFUSE_PUBLIC_KEY"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("USE_EMBEDDINGS", "false")
    monkeypatch.setenv("USE_PLAYWRIGHT", "false")
    monkeypatch.setenv("USE_DDG", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    from talent_agent.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def brief():
    return HiringBrief(
        title="Sales Team Lead",
        location="Cairo, Egypt",
        must_have=["real estate", "team leadership"],
        nice_to_have=["CRM"],
        target_companies=["Palm Hills", "SODIC"],
        exclusions=["Nawy"],
        min_years=5,
    )


def profile(name="Ahmed Samir", company="Palm Hills", url="https://www.linkedin.com/in/ahmed-samir/"):
    return Profile(
        name=name,
        current_title="Sales Team Leader",
        company=company,
        city="New Cairo",
        years_experience=8,
        skills=["real estate", "team leadership", "CRM"],
        achievements=["Led a team of 12 closing EGP 400M in 2025"],
        profile_url=url,
        raw_text="Sales Team Leader at Palm Hills. real estate sales, team leadership, CRM. Led a team of 12.",
    )


def test_rule_based_rubric_weights_sum_to_one(brief):
    c = parse_brief(brief)
    assert abs(sum(r.weight for r in c.rubric) - 1) < 0.01
    assert "New Cairo" in c.location_aliases
    assert not any(w in r.name.lower() for r in c.rubric for w in ("age", "gender", "religion"))


def test_queries_cover_sites_companies_and_semantic(brief):
    qs = query_planner.plan_queries(parse_brief(brief))
    texts = " ".join(q.text for q in qs)
    assert "site:linkedin.com/in" in texts and "Palm Hills" in texts
    assert any(q.engine == "exa" for q in qs)
    assert '-"Nawy"' in texts
    assert len({q.text for q in qs}) == len(qs)


def test_scrub_removes_contact_data():
    out = extractor.scrub("Call 01012345678 or mail ahmed@x.com")
    assert "0101" not in out and "@" not in out


def test_heuristic_extraction_from_linkedin_title():
    hit = SearchHit(
        url="https://linkedin.com/in/x", title="Mona Adel - Sales Manager - SODIC | LinkedIn", snippet="10 years in Cairo", source="tavily"
    )
    p = extractor.extract_profiles([hit])[0]
    assert (p.name, p.current_title, p.company) == ("Mona Adel", "Sales Manager", "SODIC")


def test_dedup_by_url_and_fuzzy_name():
    known = [dedup.Known(key="ats:1", name="Ahmed Samir", company="Palm Hills Developments", url="")]
    a = profile()
    b = profile(name="Sara Ali", url="https://eg.linkedin.com/in/sara")
    c = profile(name="Sara Ali", url="https://www.linkedin.com/in/sara/?trk=x")
    keep, dropped = dedup.dedupe([a, b, c], known)
    assert [p.name for p in keep] == ["Sara Ali"]
    assert {k for _, k in dropped} == {"ats:1", "run:https://eg.linkedin.com/in/sara"}


def test_load_ats_csv(tmp_path):
    f = tmp_path / "ats.csv"
    pd.DataFrame({"Full Name": ["X Y"], "Company": ["Z"], "LinkedIn": ["https://linkedin.com/in/xy"]}).to_csv(f, index=False)
    known = dedup.load_ats(str(f))
    assert known[0].name == "X Y" and known[0].url.endswith("/xy")


def test_scoring_ranks_relevant_profile_higher(brief):
    c = parse_brief(brief)
    good = profile()
    bad = Profile(name="Omar", current_title="Chef", company="Hotel", city="Hurghada", profile_url="u2", raw_text="cooking pastry")
    ranked = scoring.score_all(c, [bad, good])
    assert ranked[0].profile.name == "Ahmed Samir"
    assert ranked[0].fit_score > ranked[1].fit_score


def test_failed_must_have_caps_score(brief):
    c = parse_brief(brief)
    scores = [CriterionScore(criterion=r.name, score=1.0) for r in c.rubric]
    full = scoring.weighted(c, scores)
    scores[0].score = 0.0
    assert scoring.weighted(c, scores) < full * 0.6


def test_ungrounded_evidence_penalized():
    p = profile()
    s = scoring._ground([CriterionScore(criterion="x", score=1.0, evidence="Won President's Club 2019")], p)
    assert s[0].score == 0.5 and s[0].evidence.startswith("[unverified]")


def test_exports(brief):
    cands = [
        ScoredCandidate(profile=profile(), fit_score=0.8, status="approved", outreach_draft="Hi"),
        ScoredCandidate(profile=profile(name="B", url="u"), fit_score=0.4, status="rejected"),
    ]
    xlsx = export.to_excel(cands, SearchReport(hits=3))
    assert xlsx[:2] == b"PK"
    csv = export.to_ats_csv(cands).decode("utf-8-sig")
    assert "Ahmed Samir" in csv and "\nB," not in csv


def test_graph_end_to_end_with_interrupt(brief, monkeypatch):
    from talent_agent import graph as g
    from talent_agent import researcher

    hits = [
        SearchHit(
            url="https://linkedin.com/in/a",
            title="Ahmed Samir - Sales Team Leader - Palm Hills | LinkedIn",
            content="Sales Team Leader in New Cairo. real estate, team leadership, CRM. 8 years",
            source="tavily",
        ),
        SearchHit(
            url="https://linkedin.com/in/b",
            title="Hany Fouad - Sales Manager - Nawy | LinkedIn",
            content="Nawy real estate",
            source="tavily",
        ),
    ]
    monkeypatch.setattr(researcher, "search", lambda q, r: hits)
    monkeypatch.setattr(researcher, "enrich", lambda h, r: h)
    graph = g.build_graph()
    state = g.start(graph, brief, "Nawy", "t1")
    names = [c.profile.name for c in state["candidates"]]
    assert names == ["Ahmed Samir"]  # Nawy excluded
    assert "excel" not in state  # paused at approval
    final = g.resume(graph, "t1", {"https://linkedin.com/in/a": {"status": "approved", "draft": "Edited message"}})
    assert final["candidates"][0].status == "edited"
    assert final["run_id"] >= 1 and final["excel"][:2] == b"PK"


def test_job_ads_are_not_profiles():
    hit = SearchHit(url="https://www.bayt.com/en/egypt/jobs/sales-team-leader-1/", title="Sales Team Leader job in Cairo", snippet="hiring")
    assert extractor.extract_profiles([hit]) == []


def test_ddg_fallback_without_paid_keys(brief, monkeypatch):
    from talent_agent import researcher
    from talent_agent.config import get_settings

    monkeypatch.setenv("USE_DDG", "true")
    get_settings.cache_clear()
    calls = []
    monkeypatch.setattr(
        researcher,
        "_ddg",
        lambda q, timeout=20: (
            calls.append(q) or [SearchHit(url=f"https://linkedin.com/in/x{len(calls)}?trk=1", source="duckduckgo", query=q.text)]
        ),
    )
    qs = query_planner.plan_queries(parse_brief(brief))
    report = SearchReport()
    hits = researcher.search(qs, report)
    assert calls and all(q.kind == "boolean" for q in calls)  # semantic queries need Exa
    assert report.hits == len(hits) == len(calls) and report.sources == {"duckduckgo": len(calls)}


def test_llm_provider_auto(monkeypatch):
    from talent_agent import llm
    from talent_agent.config import get_settings

    assert llm.provider() == "none" and not llm.LLM().enabled
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    get_settings.cache_clear()
    assert llm.provider() == "gemini"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "y")
    get_settings.cache_clear()
    assert llm.provider() == "anthropic"


class FakeLLM:
    """Answers batched calls for the first item only, so the rest must fall back to rules."""

    enabled = True

    def structured(self, system, prompt, schema, max_tokens=0):
        name = schema.__name__
        if name == "ExtractionBatch":
            return schema(pages=[{"index": 0, "is_profile": True, "name": "LLM Name", "current_title": "Sales Team Leader"}])
        if name == "JudgeBatch":
            return schema(
                candidates=[{"index": 0, "criteria": [{"criterion": "Must-have skills", "score": 1.0, "evidence": "made up quote"}]}]
            )
        return schema(drafts=[{"index": 0, "message": "LLM draft"}])


def test_batched_llm_calls_map_by_index_and_fall_back(brief):
    from talent_agent import outreach

    assert extractor.batched([0, 1, 2], [9000, 9000, 10], max_chars=15000) == [[0], [1, 2]]
    hits = [
        SearchHit(url="https://linkedin.com/in/a", title="A", snippet="x"),
        SearchHit(url="https://linkedin.com/in/b", title="Mona Adel - Sales Manager - SODIC | LinkedIn", snippet="Cairo"),
    ]
    profiles = extractor.extract_profiles(hits, llm=FakeLLM())
    assert [p.name for p in profiles] == ["LLM Name", "Mona Adel"]  # second one from the rule parser

    c = parse_brief(brief)
    judged = scoring.judge_all(c, profiles, FakeLLM())
    assert judged[0][0].evidence.startswith("[unverified]") and judged[0][0].score == 0.5
    role = next(s for s in judged[0] if s.criterion == "Role match")  # missing from LLM output, added by rules
    assert role.score == 1.0
    assert len(judged[1]) == len(c.rubric)  # keyword fallback scores every criterion

    cands = outreach.draft_all(brief, [ScoredCandidate(profile=p) for p in profiles], "Nawy", llm=FakeLLM())
    assert cands[0].outreach_draft == "LLM draft" and cands[1].outreach_draft.startswith("Hi Mona")
