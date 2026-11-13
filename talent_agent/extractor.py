"""Page text -> Profile with professional fields only."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel

from talent_agent.config import get_settings
from talent_agent.llm import LLM
from talent_agent.models import Profile, SearchHit

log = logging.getLogger(__name__)

SYSTEM = """Extract professional profiles from public web pages. Each page is marked [index].
For EACH page return one item with its index. Return ONLY professional fields: name, current title,
company, listed city, years of experience, skills, concrete achievements (numbers where stated), one-line summary.
NEVER extract phone, email, home address, age, salary, family, religion, health or photos.
If a page is not a single person's professional profile (job ad, company page, list), set is_profile=false.
Do not invent facts. Leave unknown fields empty."""


class Extraction(BaseModel):
    index: int
    is_profile: bool
    name: str = ""
    current_title: str = ""
    company: str = ""
    city: str = ""
    years_experience: float | None = None
    skills: list[str] = []
    achievements: list[str] = []
    summary: str = ""


class ExtractionBatch(BaseModel):
    pages: list[Extraction]


PII = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    re.compile(r"(?:\+?20|0)1[0125]\d{8}"),
    re.compile(r"\+?\d[\d\s-]{8,}\d"),
]


def scrub(text: str) -> str:
    for rx in PII:
        text = rx.sub("[redacted]", text)
    return text


def extract_profiles(hits: list[SearchHit], llm: LLM | None = None) -> list[Profile]:
    """Several pages per LLM call (free-tier rate limits); rule-based parse for anything the LLM misses."""
    s = get_settings()
    llm = llm or LLM(fast=True)
    hits = hits[: s.max_pages]
    texts = [scrub((h.content or h.snippet)[:6000]) for h in hits]
    got: dict[int, Extraction] = {}
    if llm.enabled:
        batches = batched(list(range(len(hits))), [len(t) for t in texts])
        with ThreadPoolExecutor(max_workers=3) as pool:
            for result in pool.map(lambda b: _extract_batch(b, hits, texts, llm), batches):
                got.update(result)
    out = []
    for i, (hit, text) in enumerate(zip(hits, texts, strict=True)):
        e = got.get(i)
        if e is None:
            p = _heuristic(hit, text)
        elif e.is_profile and e.name:
            p = Profile(**e.model_dump(exclude={"index", "is_profile"}), profile_url=hit.url, source=hit.source, raw_text=text)
        else:
            p = None
        if p:
            out.append(p)
    return out


def batched(idx: list[int], sizes: list[int], max_items: int = 10, max_chars: int = 15000) -> list[list[int]]:
    """Group items into LLM calls by count and total text size."""
    out: list[list[int]] = []
    cur: list[int] = []
    chars = 0
    for i in idx:
        if cur and (len(cur) >= max_items or chars + sizes[i] > max_chars):
            out.append(cur)
            cur, chars = [], 0
        cur.append(i)
        chars += sizes[i]
    return out + [cur] if cur else out


def _extract_batch(idx: list[int], hits: list[SearchHit], texts: list[str], llm: LLM) -> dict[int, Extraction]:
    prompt = "\n\n".join(f"[{i}] URL: {hits[i].url}\nTITLE: {hits[i].title}\n{texts[i]}" for i in idx)
    try:
        res = llm.structured(SYSTEM, prompt, ExtractionBatch, max_tokens=800 * len(idx))
        return {e.index: e for e in res.pages if e.index in idx}
    except Exception as exc:
        log.warning("extract batch failed (%d pages): %s", len(idx), exc)
        return {}


CITIES = [
    "New Cairo", "Sheikh Zayed", "6th of October", "Nasr City", "Heliopolis", "Maadi", "New Capital",
    "Cairo", "Giza", "Alexandria", "North Coast", "Dubai", "Abu Dhabi", "Riyadh", "Jeddah",
]  # fmt: skip
CITY_RX = re.compile("|".join(re.escape(c) for c in CITIES), re.I)
JOB_AD_RX = re.compile(r"/jobs?/|\bjobs?\b|\bhiring\b|\bvacanc", re.I)


def _heuristic(hit: SearchHit, text: str) -> Profile | None:
    """LinkedIn-style titles: 'Name - Title - Company | LinkedIn'. Job ads and listings are skipped."""
    if JOB_AD_RX.search(hit.url) or JOB_AD_RX.search(hit.title):
        return None
    title = re.sub(r"\s*[|–-]\s*LinkedIn.*$", "", hit.title)
    title = re.split(r"\s*(?:\.\.\.|…)", title)[0].strip()  # search engines truncate long titles
    parts = [p.strip() for p in re.split(r"\s+[-–|]\s+", title) if p.strip()]
    if not parts or len(parts[0].split()) > 5:
        return None
    if len(parts) == 2 and " at " in parts[1]:  # 'Name - Title at Company'
        parts[1:] = [x.strip() for x in parts[1].split(" at ", 1)]
    m = re.search(r"(\d{1,2})\+?\s+years", text, re.I)
    cm = CITY_RX.search(f"{hit.title} {text}")
    city = next((c for c in CITIES if cm and c.lower() == cm.group(0).lower()), "")
    return Profile(
        name=parts[0],
        current_title=parts[1] if len(parts) > 1 else "",
        company=parts[2] if len(parts) > 2 else "",
        city=city,
        years_experience=float(m.group(1)) if m else None,
        summary=hit.snippet[:300],
        profile_url=hit.url,
        source=hit.source,
        raw_text=text,
    )
