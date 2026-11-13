"""Pydantic schemas shared by every pipeline stage."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


class Seniority(str, Enum):
    junior = "junior"
    mid = "mid"
    senior = "senior"
    lead = "lead"
    manager = "manager"
    director = "director"
    executive = "executive"


class HiringBrief(BaseModel):
    """Raw brief as typed by the hiring manager in the UI form."""

    title: str
    seniority: Seniority = Seniority.senior
    location: str
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    target_companies: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    min_years: int | None = None
    notes: str = ""
    max_candidates: int = 25


class Criterion(BaseModel):
    name: str
    description: str
    weight: float = Field(ge=0, le=1)
    must_have: bool = False


class SearchCriteria(BaseModel):
    """Structured criteria + scoring rubric produced by the brief parser."""

    title: str
    title_synonyms_en: list[str] = Field(default_factory=list)
    title_synonyms_ar: list[str] = Field(default_factory=list)
    location: str
    location_aliases: list[str] = Field(default_factory=list)
    seniority: Seniority
    min_years: int | None = None
    skills: list[str] = Field(default_factory=list)
    target_companies: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    rubric: list[Criterion] = Field(default_factory=list)


class SearchQuery(BaseModel):
    text: str
    kind: str = "boolean"  # boolean | semantic
    language: str = "en"
    engine: str = "tavily"  # tavily | exa


class SearchHit(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""
    content: str = ""
    source: str = ""
    query: str = ""


class Profile(BaseModel):
    """Professional fields only. No contact, salary or personal-life data (PDPL 151/2020)."""

    name: str
    current_title: str = ""
    company: str = ""
    city: str = ""
    years_experience: float | None = None
    skills: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    summary: str = ""
    profile_url: str
    source: str = ""
    raw_text: str = Field(default="", exclude=True)


class CriterionScore(BaseModel):
    criterion: str
    score: float = Field(ge=0, le=1)
    evidence: str = ""  # verbatim quote from profile text


class ScoredCandidate(BaseModel):
    profile: Profile
    embedding_similarity: float = 0.0
    judge_score: float = 0.0
    fit_score: float = 0.0
    criteria: list[CriterionScore] = Field(default_factory=list)
    outreach_draft: str = ""
    status: str = "pending"  # pending | approved | rejected | edited
    duplicate_of: str | None = None


class SearchReport(BaseModel):
    queries: list[SearchQuery] = Field(default_factory=list)
    sources: dict[str, int] = Field(default_factory=dict)
    hits: int = 0
    pages_fetched: int = 0
    fetch_failures: int = 0
    profiles_extracted: int = 0
    duplicates_removed: int = 0
    shortlisted: int = 0
    token_cost_usd: float = 0.0


__all__ = [
    "HttpUrl",
    "Seniority",
    "HiringBrief",
    "Criterion",
    "SearchCriteria",
    "SearchQuery",
    "SearchHit",
    "Profile",
    "CriterionScore",
    "ScoredCandidate",
    "SearchReport",
]
