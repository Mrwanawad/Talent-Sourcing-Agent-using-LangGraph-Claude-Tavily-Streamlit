"""Hiring brief -> structured criteria + weighted scoring rubric."""

from __future__ import annotations

import logging

from talent_agent.llm import LLM
from talent_agent.models import Criterion, HiringBrief, SearchCriteria

log = logging.getLogger(__name__)

SYSTEM = """You are a senior technical recruiter in Egypt and the Gulf.
Turn a hiring brief into structured search criteria and a scoring rubric.
Rules:
- Title synonyms in English and Egyptian Arabic job-market usage.
- Location aliases (e.g. Cairo: New Cairo, 6th of October, Sheikh Zayed, Giza, القاهرة).
- Rubric: 4-7 criteria, weights sum to 1.0, must-haves flagged.
- NEVER include protected attributes (age, gender, religion, nationality, marital status,
  health, appearance) as criteria. Years of experience is allowed only as a professional range."""

LOCATION_ALIASES = {
    "cairo": ["Cairo", "New Cairo", "Giza", "6th of October", "Sheikh Zayed", "Nasr City", "القاهرة"],
    "alexandria": ["Alexandria", "Alex", "الإسكندرية"],
    "dubai": ["Dubai", "UAE", "دبي"],
    "riyadh": ["Riyadh", "KSA", "الرياض"],
}


def parse_brief(brief: HiringBrief, llm: LLM | None = None) -> SearchCriteria:
    llm = llm or LLM()
    if llm.enabled:
        try:
            criteria = llm.structured(SYSTEM, brief.model_dump_json(indent=2), SearchCriteria)
            return _normalize(criteria, brief)
        except Exception as exc:  # degrade to rule-based so a run never dies here
            log.warning("LLM brief parse failed, using rules: %s", exc)
    return _rule_based(brief)


def _normalize(c: SearchCriteria, brief: HiringBrief) -> SearchCriteria:
    # Role and location are hard filters for sourcing; the LLM sometimes leaves them out of the rubric.
    names = " ".join(r.name.lower() for r in c.rubric)
    if "role" not in names and "title" not in names:
        c.rubric.insert(
            0, Criterion(name="Role match", description=f"Current/recent title matches {brief.title}", weight=0.25, must_have=True)
        )
    if "location" not in names:
        c.rubric.insert(1, Criterion(name="Location", description=f"Based in or near {brief.location}", weight=0.15, must_have=True))
    if not c.location_aliases:
        c.location_aliases = LOCATION_ALIASES.get(brief.location.split(",")[0].strip().lower(), [brief.location])
    total = sum(r.weight for r in c.rubric) or 1.0
    for r in c.rubric:
        r.weight = round(r.weight / total, 3)
    c.exclusions = sorted(set(c.exclusions) | set(brief.exclusions))
    c.target_companies = sorted(set(c.target_companies) | set(brief.target_companies))
    if brief.min_years and not c.min_years:
        c.min_years = brief.min_years
    return c


def _rule_based(brief: HiringBrief) -> SearchCriteria:
    rubric: list[Criterion] = [
        Criterion(name="Role match", description=f"Current/recent title matches {brief.title}", weight=0.3, must_have=True),
        Criterion(name="Location", description=f"Based in or near {brief.location}", weight=0.15, must_have=True),
    ]
    if brief.must_have:
        rubric.append(Criterion(name="Must-have skills", description=", ".join(brief.must_have), weight=0.3, must_have=True))
    if brief.nice_to_have:
        rubric.append(Criterion(name="Nice-to-have skills", description=", ".join(brief.nice_to_have), weight=0.1))
    rubric.append(
        Criterion(name="Seniority & track record", description=f"{brief.seniority.value} level with measurable achievements", weight=0.15)
    )
    total = sum(r.weight for r in rubric)
    for r in rubric:
        r.weight = round(r.weight / total, 3)

    return SearchCriteria(
        title=brief.title,
        title_synonyms_en=_synonyms(brief.title),
        title_synonyms_ar=[],
        location=brief.location,
        location_aliases=LOCATION_ALIASES.get(brief.location.split(",")[0].strip().lower(), [brief.location]),
        seniority=brief.seniority,
        min_years=brief.min_years,
        skills=brief.must_have + brief.nice_to_have,
        target_companies=brief.target_companies,
        exclusions=brief.exclusions,
        rubric=rubric,
    )


def _synonyms(title: str) -> list[str]:
    t = title.split(",")[0].strip()
    out = [t]
    swaps = {"Team Lead": ["Team Leader", "Supervisor"], "Manager": ["Head of", "Lead"], "Sales": ["Business Development"]}
    for k, vals in swaps.items():
        if k.lower() in t.lower():
            out += [t.replace(k, v) for v in vals]
    return list(dict.fromkeys(out))
