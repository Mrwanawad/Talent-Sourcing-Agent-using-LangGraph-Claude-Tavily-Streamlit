"""LangGraph pipeline. Pauses at human approval (interrupt) before anything is exported."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from talent_agent import dedup, export, extractor, outreach, query_planner, researcher, scoring, storage
from talent_agent.brief_parser import parse_brief
from talent_agent.config import get_settings
from talent_agent.llm import meter
from talent_agent.models import (
    HiringBrief,
    Profile,
    ScoredCandidate,
    SearchCriteria,
    SearchHit,
    SearchQuery,
    SearchReport,
)
from talent_agent.observability import flush, observe

log = logging.getLogger(__name__)

MODELS = [
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


class State(TypedDict, total=False):
    brief: HiringBrief
    company: str
    criteria: SearchCriteria
    queries: list[SearchQuery]
    hits: list[SearchHit]
    profiles: list[Profile]
    candidates: list[ScoredCandidate]
    report: SearchReport
    run_id: int
    cost_start: float
    excel: bytes
    ats_csv: bytes


def n_parse(s: State) -> dict[str, Any]:
    # meter is process-wide (Streamlit serves many runs); remember where this run started
    return {"cost_start": meter.usd, "criteria": parse_brief(s["brief"]), "report": SearchReport()}


def n_plan(s: State) -> dict[str, Any]:
    return {"queries": query_planner.plan_queries(s["criteria"])}


def n_research(s: State) -> dict[str, Any]:
    report = s["report"]
    hits = researcher.search(s["queries"], report)
    return {"hits": researcher.enrich(hits, report), "report": report}


def n_extract(s: State) -> dict[str, Any]:
    profiles = extractor.extract_profiles(s["hits"])
    excl = [e.lower() for e in s["criteria"].exclusions]
    profiles = [p for p in profiles if not any(e and e in p.company.lower() for e in excl)]
    s["report"].profiles_extracted = len(profiles)
    return {"profiles": profiles, "report": s["report"]}


def n_dedup(s: State) -> dict[str, Any]:
    known = dedup.load_ats(get_settings().ats_csv_path) + storage.previous_candidates()
    keep, dropped = dedup.dedupe(s["profiles"], known)
    s["report"].duplicates_removed = len(dropped)
    return {"profiles": keep, "report": s["report"]}


def n_score(s: State) -> dict[str, Any]:
    ranked = scoring.score_all(s["criteria"], s["profiles"])
    top = ranked[: s["brief"].max_candidates]
    s["report"].shortlisted = len(top)
    return {"candidates": top, "report": s["report"]}


def n_outreach(s: State) -> dict[str, Any]:
    return {"candidates": outreach.draft_all(s["brief"], s["candidates"], s.get("company", "our company"))}


def n_approval(s: State) -> dict[str, Any]:
    """Human-in-the-loop. Resume with {profile_url: {"status": ..., "draft": ...}}."""
    decisions: dict[str, dict] = interrupt({"candidates": [c.model_dump(mode="json") for c in s["candidates"]]})["decisions"]
    for c in s["candidates"]:
        d = decisions.get(c.profile.profile_url)
        if not d:
            continue
        c.status = d.get("status", c.status)
        if d.get("draft") and d["draft"] != c.outreach_draft:
            c.outreach_draft = d["draft"]
            c.status = "edited" if c.status != "rejected" else c.status
    return {"candidates": s["candidates"]}


def n_export(s: State) -> dict[str, Any]:
    report = s["report"]
    report.token_cost_usd = round(meter.usd - s.get("cost_start", 0.0), 6)
    run_id = storage.save_run(s["brief"], report, s["candidates"])
    flush()
    return {
        "run_id": run_id,
        "report": report,
        "excel": export.to_excel(s["candidates"], report),
        "ats_csv": export.to_ats_csv(s["candidates"]),
    }


def build_graph(checkpointer=None):
    g = StateGraph(State)
    for name, fn in [
        ("parse", n_parse),
        ("plan", n_plan),
        ("research", n_research),
        ("extract", n_extract),
        ("dedup", n_dedup),
        ("score", n_score),
        ("outreach", n_outreach),
        ("approval", n_approval),
        ("export", n_export),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "parse")
    g.add_edge("parse", "plan")
    g.add_edge("plan", "research")
    g.add_edge("research", "extract")
    g.add_edge("extract", "dedup")
    g.add_edge("dedup", "score")
    g.add_edge("score", "outreach")
    g.add_edge("outreach", "approval")
    g.add_edge("approval", "export")
    g.add_edge("export", END)
    serde = JsonPlusSerializer(allowed_msgpack_modules=[("talent_agent.models", n) for n in MODELS])
    return g.compile(checkpointer=checkpointer or MemorySaver(serde=serde))


@observe(name="talent_sourcing.run")
def start(graph, brief: HiringBrief, company: str, thread_id: str) -> dict:
    """Runs until the approval interrupt. Returns state snapshot values."""
    for _ in stream_stages(graph, brief, company, thread_id):
        pass
    return snapshot(graph, thread_id)


def stream_stages(graph, brief: HiringBrief, company: str, thread_id: str):
    """Yields each node name as it finishes, so the UI can show live progress. Stops at the approval interrupt."""
    cfg = {"configurable": {"thread_id": thread_id}}
    for chunk in graph.stream({"brief": brief, "company": company}, cfg, stream_mode="updates"):
        yield from (node for node in chunk if not node.startswith("__"))


def snapshot(graph, thread_id: str) -> dict:
    return graph.get_state({"configurable": {"thread_id": thread_id}}).values


def resume(graph, thread_id: str, decisions: dict[str, dict]) -> dict:
    cfg = {"configurable": {"thread_id": thread_id}}
    graph.invoke(Command(resume={"decisions": decisions}), cfg)
    return graph.get_state(cfg).values
