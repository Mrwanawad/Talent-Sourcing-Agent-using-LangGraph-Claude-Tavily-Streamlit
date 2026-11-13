"""Excel shortlist + ATS CSV."""

from __future__ import annotations

import io

import pandas as pd

from talent_agent.models import ScoredCandidate, SearchReport


def to_frame(cands: list[ScoredCandidate]) -> pd.DataFrame:
    rows = []
    for c in cands:
        p = c.profile
        rows.append(
            {
                "name": p.name,
                "current_title": p.current_title,
                "company": p.company,
                "city": p.city,
                "years_experience": p.years_experience,
                "achievements": "; ".join(p.achievements),
                "profile_url": p.profile_url,
                "fit_score": c.fit_score,
                "judge_score": c.judge_score,
                "embedding_similarity": c.embedding_similarity,
                "evidence": "\n".join(f"{s.criterion}: {s.score:.2f} | {s.evidence}" for s in c.criteria),
                "outreach_draft": c.outreach_draft,
                "status": c.status,
            }
        )
    return pd.DataFrame(rows)


def to_excel(cands: list[ScoredCandidate], report: SearchReport) -> bytes:
    buf = io.BytesIO()
    df = to_frame(cands)
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        df.to_excel(xw, sheet_name="Shortlist", index=False)
        ws = xw.sheets["Shortlist"]
        wrap = xw.book.add_format({"text_wrap": True, "valign": "top"})
        widths = {
            "name": 22,
            "current_title": 28,
            "company": 22,
            "achievements": 45,
            "profile_url": 40,
            "evidence": 60,
            "outreach_draft": 60,
        }
        for i, col in enumerate(df.columns):
            ws.set_column(i, i, widths.get(col, 14), wrap)
        ws.freeze_panes(1, 1)
        if len(df):
            ws.autofilter(0, 0, len(df), len(df.columns) - 1)
            idx = df.columns.get_loc("fit_score")
            ws.conditional_format(1, idx, len(df), idx, {"type": "3_color_scale"})

        meta = pd.DataFrame(
            [
                ("hits", report.hits),
                ("pages_fetched", report.pages_fetched),
                ("fetch_failures", report.fetch_failures),
                ("profiles_extracted", report.profiles_extracted),
                ("duplicates_removed", report.duplicates_removed),
                ("shortlisted", report.shortlisted),
                ("token_cost_usd", round(report.token_cost_usd, 4)),
            ]
            + [(f"source:{k}", v) for k, v in report.sources.items()],
            columns=["metric", "value"],
        )
        meta.to_excel(xw, sheet_name="Search report", index=False)
        pd.DataFrame([q.model_dump() for q in report.queries]).to_excel(xw, sheet_name="Queries", index=False)
    return buf.getvalue()


def to_ats_csv(cands: list[ScoredCandidate]) -> bytes:
    """Generic ATS import: one row per approved candidate."""
    df = to_frame([c for c in cands if c.status in ("approved", "edited")])
    cols = {
        "name": "Full Name",
        "current_title": "Current Title",
        "company": "Current Company",
        "city": "Location",
        "profile_url": "Source URL",
        "fit_score": "Score",
        "outreach_draft": "Notes",
    }
    df = df.reindex(columns=list(cols)).rename(columns=cols)
    df["Source"] = "Talent-Sourcing Agent"
    return df.to_csv(index=False).encode("utf-8-sig")
