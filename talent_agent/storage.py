"""Run + candidate persistence. PostgreSQL in prod, SQLite locally (same SQLAlchemy code)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session

from talent_agent.config import get_settings
from talent_agent.dedup import Known
from talent_agent.models import HiringBrief, ScoredCandidate, SearchReport


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    brief = Column(JSON)
    report = Column(JSON)


class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, index=True)
    name = Column(String(200))
    company = Column(String(200))
    profile_url = Column(String(500), index=True)
    fit_score = Column(Float)
    status = Column(String(20), default="pending")
    payload = Column(Text)


_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
        Base.metadata.create_all(_engine)
    return _engine


def save_run(brief: HiringBrief, report: SearchReport, cands: list[ScoredCandidate]) -> int:
    with Session(engine()) as s:
        run = Run(brief=brief.model_dump(mode="json"), report=report.model_dump(mode="json"))
        s.add(run)
        s.flush()
        for c in cands:
            s.add(
                Candidate(
                    run_id=run.id,
                    name=c.profile.name,
                    company=c.profile.company,
                    profile_url=c.profile.profile_url,
                    fit_score=c.fit_score,
                    status=c.status,
                    payload=c.model_dump_json(),
                )
            )
        s.commit()
        return run.id


def update_status(run_id: int, profile_url: str, status: str, draft: str | None = None) -> None:
    with Session(engine()) as s:
        row = s.scalar(select(Candidate).where(Candidate.run_id == run_id, Candidate.profile_url == profile_url))
        if not row:
            return
        row.status = status
        if draft is not None:
            data = json.loads(row.payload)
            data["outreach_draft"] = draft
            data["status"] = status
            row.payload = json.dumps(data)
        s.commit()


def previous_candidates() -> list[Known]:
    """Everyone surfaced in earlier runs, so we don't re-pitch the same people."""
    try:
        with Session(engine()) as s:
            return [
                Known(key=f"db:{r.id}", name=r.name or "", company=r.company or "", url=r.profile_url or "")
                for r in s.scalars(select(Candidate))
            ]
    except Exception:
        return []


def decisions() -> list[tuple[float, float, int]]:
    """(embedding_similarity, judge_score, accepted) for calibration."""
    out = []
    with Session(engine()) as s:
        for r in s.scalars(select(Candidate).where(Candidate.status.in_(["approved", "edited", "rejected"]))):
            d = json.loads(r.payload)
            out.append((d["embedding_similarity"], d["judge_score"], int(r.status != "rejected")))
    return out
