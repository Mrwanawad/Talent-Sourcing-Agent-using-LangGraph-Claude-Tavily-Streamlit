"""Duplicate removal vs ATS export and previous runs (rapidfuzz)."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd
from rapidfuzz import fuzz

from talent_agent.models import Profile

NAME_THRESHOLD = 90
COMPANY_THRESHOLD = 80


@dataclass
class Known:
    key: str
    name: str
    company: str
    url: str


def normalize_url(url: str) -> str:
    url = re.sub(r"^https?://(www\.|[a-z]{2}\.)?", "", url.strip().lower())
    return url.split("?")[0].rstrip("/")


def normalize_name(name: str) -> str:
    name = re.sub(r"\b(eng|dr|mr|mrs|ms|mba|pmp)\.?\b", "", name.lower())
    return " ".join(re.sub(r"[^\w\s]", " ", name).split())


def load_ats(path: str) -> list[Known]:
    if not path:
        return []
    df = pd.read_csv(path) if path.endswith(".csv") else pd.read_excel(path)
    cols = {c.lower().strip(): c for c in df.columns}

    def col(*names):
        return next((cols[n] for n in names if n in cols), None)

    n, c, u = col("name", "full name", "candidate"), col("company", "current company"), col("profile_url", "url", "linkedin")
    return [
        Known(
            key=f"ats:{i}",
            name=str(r[n]) if n else "",
            company=str(r[c]) if c and pd.notna(r[c]) else "",
            url=str(r[u]) if u and pd.notna(r[u]) else "",
        )
        for i, r in df.iterrows()
    ]


def match(p: Profile, known: list[Known]) -> str | None:
    url = normalize_url(p.profile_url)
    name = normalize_name(p.name)
    for k in known:
        if k.url and normalize_url(k.url) == url:
            return k.key
        if name and fuzz.token_sort_ratio(name, normalize_name(k.name)) >= NAME_THRESHOLD:
            if not k.company or not p.company or fuzz.partial_ratio(p.company.lower(), k.company.lower()) >= COMPANY_THRESHOLD:
                return k.key
    return None


def dedupe(profiles: list[Profile], known: list[Known]) -> tuple[list[Profile], list[tuple[Profile, str]]]:
    """Returns (unique new profiles, [(dropped profile, matched key)])."""
    keep: list[Profile] = []
    dropped: list[tuple[Profile, str]] = []
    pool = list(known)
    for p in profiles:
        hit = match(p, pool)
        if hit:
            dropped.append((p, hit))
            continue
        keep.append(p)
        pool.append(Known(key=f"run:{p.profile_url}", name=p.name, company=p.company, url=p.profile_url))
    return keep, dropped
