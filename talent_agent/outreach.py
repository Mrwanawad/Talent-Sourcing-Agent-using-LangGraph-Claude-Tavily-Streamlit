"""Personalized outreach drafts. Never sent automatically."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel

from talent_agent.llm import LLM
from talent_agent.models import HiringBrief, ScoredCandidate

log = logging.getLogger(__name__)

SYSTEM = """Write a short recruiter outreach message (max 90 words) to EACH candidate. Each candidate is marked [index].
Reference ONE specific professional achievement or role from that candidate's profile.
Professional, warm, no hype, no emojis, no salary claims. End with a low-pressure question.
Write in English unless the profile is clearly Arabic-only. Return one message per index."""


class Draft(BaseModel):
    index: int
    message: str


class DraftBatch(BaseModel):
    drafts: list[Draft]


def template(brief: HiringBrief, cand: ScoredCandidate, company: str) -> str:
    p = cand.profile
    hook = p.achievements[0] if p.achievements else (f"your work as {p.current_title} at {p.company}" if p.company else "your background")
    first = p.name.split()[0] if p.name else "there"
    return (
        f"Hi {first}, I came across {hook} and thought of you for a {brief.title} role at {company} in {brief.location}. "
        f"The team is growing and your experience looks like a strong fit. Would you be open to a short call this week?"
    )


def _batch(brief: HiringBrief, idx: list[int], cands: list[ScoredCandidate], company: str, llm: LLM) -> dict[int, str]:
    lines = []
    for i in idx:
        p, c = cands[i].profile, cands[i]
        evidence = [s.evidence for s in c.criteria if s.score >= 0.6][:3]
        lines.append(f"[{i}] {p.name}, {p.current_title} at {p.company}, {p.city}. Achievements: {p.achievements}. Evidence: {evidence}")
    prompt = f"Hiring company: {company}\nRole: {brief.title} ({brief.location})\n\nCANDIDATES:\n" + "\n".join(lines)
    try:
        out = llm.structured(SYSTEM, prompt, DraftBatch, max_tokens=250 * len(idx))
        return {d.index: d.message.strip() for d in out.drafts if d.index in idx and d.message.strip()}
    except Exception as exc:
        log.warning("outreach batch failed (%d candidates): %s", len(idx), exc)
        return {}


def draft_all(brief: HiringBrief, cands: list[ScoredCandidate], company: str, llm: LLM | None = None) -> list[ScoredCandidate]:
    llm = llm or LLM()
    got: dict[int, str] = {}
    if llm.enabled and cands:
        batches = [list(range(i, min(i + 8, len(cands)))) for i in range(0, len(cands), 8)]
        with ThreadPoolExecutor(max_workers=3) as pool:
            for result in pool.map(lambda b: _batch(brief, b, cands, company, llm), batches):
                got.update(result)
    for i, c in enumerate(cands):
        c.outreach_draft = got.get(i) or template(brief, c, company)
    return cands
