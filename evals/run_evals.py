"""Offline evaluation against labeled data.

evals/data/labeled_profiles.jsonl  one per line: {"url", "text", "expected": {name, current_title, company, city}}
evals/data/decisions.csv           profile_url, fit_score, accepted (0/1) from hiring-manager review

Usage:
    python -m evals.run_evals extraction
    python -m evals.run_evals ranking
    python -m evals.run_evals calibrate      # fits models/calibrator.pkl from DB decisions
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

DATA = Path(__file__).parent / "data"
FIELDS = ["name", "current_title", "company", "city"]


def extraction_accuracy() -> dict[str, float]:
    from talent_agent.extractor import extract_profiles
    from talent_agent.models import SearchHit

    rows = [json.loads(line) for line in (DATA / "labeled_profiles.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    hits = [SearchHit(url=r["url"], title=r.get("title", ""), content=r["text"]) for r in rows]
    got = {p.profile_url: p for p in extract_profiles(hits)}
    correct = dict.fromkeys(FIELDS, 0)
    for r in rows:
        p = got.get(r["url"])
        if not r["expected"].get("name"):  # negative example: correct only if nothing was extracted
            for f in FIELDS:
                correct[f] += p is None
            continue
        for f in FIELDS:
            if p and fuzz.token_sort_ratio(str(getattr(p, f)).lower(), str(r["expected"].get(f, "")).lower()) >= 85:
                correct[f] += 1
    return {f: round(c / len(rows), 3) for f, c in correct.items()}


def ranking_metrics(k: int = 10) -> dict[str, float]:
    df = pd.read_csv(DATA / "decisions.csv").sort_values("fit_score", ascending=False)
    return {
        "acceptance_rate": round(float(df["accepted"].mean()), 3),
        f"precision@{k}": round(float(df.head(k)["accepted"].mean()), 3),
    }


def calibrate() -> str:
    from talent_agent import scoring, storage

    rows = storage.decisions()
    if len({r[2] for r in rows}) < 2:
        return f"need both accepted and rejected decisions, have {len(rows)} rows"
    scoring.fit_calibrator([(a, b) for a, b, _ in rows], [y for *_, y in rows])
    return f"calibrator fitted on {len(rows)} decisions -> {scoring.CALIBRATOR_PATH}"


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ranking"
    print({"extraction": extraction_accuracy, "ranking": ranking_metrics, "calibrate": calibrate}[cmd]())
