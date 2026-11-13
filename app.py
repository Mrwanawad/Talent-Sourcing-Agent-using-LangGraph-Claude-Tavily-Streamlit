"""Streamlit UI: brief form -> shortlist review -> approve/edit/reject -> Excel + ATS CSV."""

from __future__ import annotations

import uuid

import pandas as pd
import streamlit as st

from talent_agent.graph import build_graph, resume, start
from talent_agent.models import HiringBrief, ScoredCandidate, Seniority

st.set_page_config(page_title="Talent Sourcing Agent", layout="wide")


@st.cache_resource
def graph():
    return build_graph()


def lines(text: str) -> list[str]:
    return [x.strip() for x in text.replace(",", "\n").splitlines() if x.strip()]


st.title("Talent Sourcing Agent")
st.caption("Hiring brief to evidence-scored shortlist. A recruiter approves every contact; nothing is sent automatically.")

with st.sidebar:
    st.header("Hiring brief")
    with st.form("brief"):
        company = st.text_input("Hiring company", "Nawy")
        title = st.text_input("Role title", "Sales Team Lead")
        location = st.text_input("Location", "Cairo, Egypt")
        seniority = st.selectbox("Seniority", [s.value for s in Seniority], index=3)
        min_years = st.number_input("Min years of experience", 0, 30, 5)
        must = st.text_area("Must-have skills (one per line)", "real estate sales\nteam leadership\nCRM")
        nice = st.text_area("Nice-to-have", "proptech\nArabic and English")
        targets = st.text_area("Target companies", "Palm Hills\nEmaar Misr\nSODIC\nColdwell Banker")
        excl = st.text_area("Exclusions (companies)", "")
        max_c = st.slider("Shortlist size", 5, 50, 20)
        go = st.form_submit_button("Run search", type="primary")

if go:
    brief = HiringBrief(
        title=title,
        location=location,
        seniority=Seniority(seniority),
        min_years=int(min_years) or None,
        must_have=lines(must),
        nice_to_have=lines(nice),
        target_companies=lines(targets),
        exclusions=lines(excl),
        max_candidates=max_c,
    )
    st.session_state.thread = str(uuid.uuid4())
    with st.status("Sourcing candidates...", expanded=True) as status:
        st.write("Parsing brief, planning queries, searching, extracting, scoring, drafting...")
        st.session_state.state = start(graph(), brief, company, st.session_state.thread)
        st.session_state.pop("final", None)
        status.update(label="Shortlist ready for review", state="complete")

state = st.session_state.get("state")
if state and "final" not in st.session_state:
    report = state["report"]
    crit = state["criteria"]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Search hits", report.hits)
    c2.metric("Profiles", report.profiles_extracted)
    c3.metric("Duplicates removed", report.duplicates_removed)
    c4.metric("Shortlisted", report.shortlisted)
    c5.metric("Fetch failures", report.fetch_failures)

    with st.expander("Criteria and rubric"):
        st.json(crit.model_dump(mode="json"))
    with st.expander(f"Queries ({len(state['queries'])})"):
        st.dataframe(pd.DataFrame([q.model_dump() for q in state["queries"]]), width="stretch")

    cands: list[ScoredCandidate] = state.get("candidates", [])
    if not cands:
        st.warning(
            "No candidates found. Search returned nothing (DuckDuckGo may be rate-limiting). Add TAVILY_API_KEY / EXA_API_KEY or widen the brief."
        )
    decisions: dict[str, dict] = {}
    for i, c in enumerate(cands):
        p = c.profile
        with st.container(border=True):
            left, right = st.columns([3, 2])
            with left:
                st.markdown(f"**{i + 1}. {p.name}** · {p.current_title} · {p.company} · {p.city}")
                st.caption(
                    f"Fit {c.fit_score:.2f} (judge {c.judge_score:.2f}, embedding {c.embedding_similarity:.2f}) · [profile]({p.profile_url})"
                )
                st.dataframe(pd.DataFrame([s.model_dump() for s in c.criteria]), hide_index=True, width="stretch")
            with right:
                draft = st.text_area("Outreach draft", c.outreach_draft, key=f"d{i}", height=160)
                status = st.radio("Decision", ["pending", "approved", "rejected"], key=f"s{i}", horizontal=True)
            decisions[p.profile_url] = {"status": status, "draft": draft}

    if cands and st.button("Submit decisions and export", type="primary"):
        st.session_state.final = resume(graph(), st.session_state.thread, decisions)
        st.rerun()

final = st.session_state.get("final")
if final:
    st.success(f"Run #{final['run_id']} saved. Token cost ${final['report'].token_cost_usd:.4f}")
    st.download_button("Download shortlist (Excel)", final["excel"], "shortlist.xlsx")
    st.download_button("Download ATS CSV (approved only)", final["ats_csv"], "ats_import.csv", "text/csv")
    if st.button("New search"):
        for k in ("state", "final", "thread"):
            st.session_state.pop(k, None)
        st.rerun()
