"""Headless run: python run_cli.py brief.json --company Nawy --approve-top 10"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from talent_agent.graph import build_graph, resume, start
from talent_agent.models import HiringBrief


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Arabic/Cyrillic names on Windows consoles
    ap = argparse.ArgumentParser()
    ap.add_argument("brief", help="path to brief JSON (HiringBrief fields)")
    ap.add_argument("--company", default="Nawy")
    ap.add_argument("--approve-top", type=int, default=0, help="mark top N approved (still a human decision; default none)")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    brief = HiringBrief.model_validate_json(Path(a.brief).read_text(encoding="utf-8"))
    graph, tid = build_graph(), str(uuid.uuid4())
    state = start(graph, brief, a.company, tid)
    cands = state.get("candidates", [])
    for i, c in enumerate(cands, 1):
        print(f"{i:>2}. {c.fit_score:.2f}  {c.profile.name} | {c.profile.current_title} | {c.profile.company} | {c.profile.profile_url}")

    decisions = {c.profile.profile_url: {"status": "approved"} for c in cands[: a.approve_top]}
    final = resume(graph, tid, decisions)
    out = Path(a.out)
    out.mkdir(exist_ok=True)
    (out / "shortlist.xlsx").write_bytes(final["excel"])
    (out / "ats_import.csv").write_bytes(final["ats_csv"])
    print(json.dumps(final["report"].model_dump(exclude={"queries"}), indent=2))


if __name__ == "__main__":
    main()
