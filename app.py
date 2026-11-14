"""Streamlit UI for recruiters: brief -> live sourcing -> shortlist review -> approve/edit/reject -> export + contact queue."""

from __future__ import annotations

import html
import uuid

import pandas as pd
import streamlit as st

from talent_agent.graph import build_graph, resume, snapshot, stream_stages
from talent_agent.llm import meter, provider
from talent_agent.models import HiringBrief, ScoredCandidate, SearchCriteria, Seniority
from talent_agent.presets import BROKERAGES, DEVELOPERS, LOCATIONS, ROLE_PRESETS

st.set_page_config(page_title="Talent Sourcing · Real Estate", page_icon=":material/apartment:", layout="wide")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=GFS+Didot&display=swap');
:root {
  --ink: #1E2A2F; --muted: #4F5B62; --paper: #FBF8F3; --sand: #F2ECE2; --line: #E0D6C6;
  --forest: #2F4A3A; --forest-soft: #EAF1EC; --brass: #8C6A3A; --brass-soft: #F6EEDF; --clay: #8E3B26; --clay-soft: #FBECE7;
}
html, body, .stApp, .stMarkdown, .stMarkdown p, .stMarkdown li, input, textarea, table, td, th,
[data-testid="stMetricValue"], [data-testid="stCode"] code { font-family: "Times New Roman", Times, serif; }
[data-testid="stWidgetLabel"] p, label p, th, .ts-label { font-family: "Times New Roman", Times, serif; font-weight: 700; }
h1, h2, h3, .ts-display { font-family: "GFS Didot", Didot, "Bodoni MT", serif !important; font-weight: 400 !important; color: var(--ink); }
.stButton button, .stDownloadButton button, .stFormSubmitButton button { font-family: "Times New Roman", Times, serif; font-weight: 700; }
[data-testid="stCode"] code { white-space: pre-wrap; font-size: 1rem; }
.block-container { padding-top: 2.2rem; max-width: 1280px; }

.ts-hero { border-bottom: 1px solid var(--line); padding-bottom: 1.1rem; margin-bottom: 1.2rem; }
.ts-hero h1 { font-size: 2.6rem; margin: 0 0 .3rem 0; line-height: 1.1; }
.ts-hero .ts-kicker { font-weight: 700; color: var(--brass); font-size: 1rem; }
.ts-hero p { color: var(--muted); font-size: 1.1rem; margin: .2rem 0 0 0; max-width: 860px; }

.ts-steps { display: flex; gap: .5rem; flex-wrap: wrap; margin: .2rem 0 1.2rem 0; }
.ts-step { flex: 1 1 160px; border: 1px solid var(--line); border-radius: 10px; padding: .55rem .8rem; background: #fff; color: var(--muted); }
.ts-step b { display: block; color: var(--ink); font-size: 1.02rem; }
.ts-step.done { background: var(--forest-soft); border-color: #BCD0C2; }
.ts-step.active { border: 2px solid var(--forest); background: #fff; }
.ts-step.active b { color: var(--forest); }

.ts-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .7rem; margin-bottom: 1rem; }
.ts-kpi { background: #fff; border: 1px solid var(--line); border-radius: 10px; padding: .7rem .9rem; }
.ts-kpi .v { font-family: "GFS Didot", Didot, serif; font-size: 2rem; color: var(--ink); line-height: 1.1; }
.ts-kpi .l { font-weight: 700; color: var(--muted); font-size: .95rem; }

.ts-card-head { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; }
.ts-name { font-family: "GFS Didot", Didot, serif; font-size: 1.55rem; color: var(--ink); line-height: 1.15; }
.ts-rank { color: var(--brass); font-weight: 700; margin-right: .35rem; }
.ts-meta { color: var(--muted); font-size: 1.05rem; margin-top: .15rem; }
.ts-meta a { color: var(--forest); font-weight: 700; }
.ts-fit { text-align: right; min-width: 120px; }
.ts-fit .n { font-family: "GFS Didot", Didot, serif; font-size: 2.1rem; color: var(--ink); line-height: 1; }
.ts-fit .of { color: var(--muted); font-size: .95rem; }

.chip { display: inline-block; padding: 2px 10px; border-radius: 999px; border: 1px solid var(--line); background: #fff;
        font-size: .92rem; margin: 6px 6px 0 0; color: var(--ink); }
.chip .g { font-family: "Segoe UI Symbol", "Apple Symbols", "DejaVu Sans", sans-serif; }
.ts-meta a { white-space: nowrap; }
.chip.ok { border-color: #A9C2B1; background: var(--forest-soft); color: #22402E; }
.chip.miss { border-color: #DDB0A3; background: var(--clay-soft); color: var(--clay); }
.tier { display: inline-block; padding: 2px 10px; border-radius: 6px; font-weight: 700; font-size: .9rem; margin-top: 4px; }
.tier.strong { background: var(--forest); color: #fff; }
.tier.possible { background: var(--brass-soft); color: var(--brass); border: 1px solid #E2CFA9; }
.tier.gaps { background: var(--clay-soft); color: var(--clay); border: 1px solid #DDB0A3; }

.ts-note { background: var(--sand); border: 1px solid var(--line); border-radius: 10px; padding: .8rem 1rem; color: var(--ink); }
.ts-how { background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 1rem 1.1rem; height: 100%; }
.ts-how .ts-display { font-size: 1.3rem; margin-bottom: .3rem; }
.ts-how p { color: var(--muted); margin: 0; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

STEPS = ["Hiring brief", "Sourcing", "Review shortlist", "Export & contact"]
STAGES = {
    "parse": "Brief turned into a weighted scoring rubric",
    "plan": "Search queries planned in English and Arabic",
    "research": "Public professional profiles searched",
    "extract": "Professional fields extracted (no contact or personal data)",
    "dedup": "Duplicates removed against the ATS and past runs",
    "score": "Candidates scored with quoted evidence",
    "outreach": "Personalized outreach drafts written",
}
DECISIONS = ["pending", "approved", "rejected"]
DECISION_LABELS = {"pending": "Undecided", "approved": "Approve", "rejected": "Reject"}


@st.cache_resource
def graph():
    return build_graph()


def esc(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def lines(text: str) -> list[str]:
    return [x.strip() for x in text.replace(",", "\n").splitlines() if x.strip()]


def steps(active: int) -> None:
    cells = []
    for i, name in enumerate(STEPS):
        cls = "done" if i < active else "active" if i == active else ""
        cells.append(f'<div class="ts-step {cls}"><span>Step {i + 1}</span><b>{name}</b></div>')
    st.markdown(f'<div class="ts-steps">{"".join(cells)}</div>', unsafe_allow_html=True)


def kpis(items: list[tuple[str, object]]) -> None:
    cells = "".join(f'<div class="ts-kpi"><div class="v">{esc(v)}</div><div class="l">{esc(label)}</div></div>' for label, v in items)
    st.markdown(f'<div class="ts-kpis">{cells}</div>', unsafe_allow_html=True)


def must_have_check(crit: SearchCriteria, c: ScoredCandidate) -> list[tuple[str, bool]]:
    scores = {s.criterion.lower(): s.score for s in c.criteria}
    return [(r.name, scores.get(r.name.lower(), 0.0) >= 0.3) for r in crit.rubric if r.must_have]


def tier(checks: list[tuple[str, bool]], fit: float) -> tuple[str, str]:
    missing = sum(not ok for _, ok in checks)
    if not missing:
        return ("strong", "Meets all must-haves") if fit >= 0.3 else ("possible", "Meets must-haves, thin profile")
    if missing == 1:
        return "possible", f"Missing: {next(n for n, ok in checks if not ok)}"
    return "gaps", f"Missing {missing} must-haves"


def safe_url(url: str) -> str:
    return url if url.startswith(("http://", "https://")) else ""


# ---------------------------------------------------------------- sidebar: hiring brief


def apply_preset() -> None:
    p = ROLE_PRESETS.get(st.session_state.preset)
    if not p:
        return
    st.session_state.update(
        f_title=st.session_state.preset,
        f_seniority=p["seniority"],
        f_years=p["min_years"],
        f_must="\n".join(p["must"]),
        f_nice="\n".join(p["nice"]),
    )


DEFAULTS = {
    "preset": "Sales Team Lead",
    "f_company": "Acme Realty",
    "f_title": "Sales Team Lead",
    "f_location": LOCATIONS[0],
    "f_seniority": "lead",
    "f_years": 5,
    "f_must": "real estate sales\nteam leadership\nCRM",
    "f_nice": "proptech\nArabic and English\noff-plan launches",
    "f_devs": ["Palm Hills", "SODIC", "Emaar Misr"],
    "f_brokers": ["Coldwell Banker"],
    "f_other": "",
    "f_excl_own": True,
    "f_excl": "",
    "f_size": 20,
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)

with st.sidebar:
    st.markdown('<div class="ts-display" style="font-size:1.6rem">Hiring brief</div>', unsafe_allow_html=True)
    st.caption("Start from a real estate role template, then adjust.")
    st.selectbox("Role template", list(ROLE_PRESETS), key="preset", on_change=apply_preset)
    with st.form("brief"):
        st.text_input("Hiring company", key="f_company")
        st.text_input("Role title", key="f_title")
        st.selectbox("Location", LOCATIONS, key="f_location")
        c1, c2 = st.columns(2)
        c1.selectbox("Seniority", [s.value for s in Seniority], key="f_seniority")
        c2.number_input("Min. years", 0, 30, key="f_years")
        st.text_area("Must-have skills", key="f_must", height=120, help="One per line. Failing a must-have halves the fit score.")
        st.text_area("Nice-to-have", key="f_nice", height=110)
        st.multiselect("Source from developers", DEVELOPERS, key="f_devs")
        st.multiselect("Source from brokerages", BROKERAGES, key="f_brokers")
        st.text_input("Other target companies", key="f_other", placeholder="comma separated")
        st.checkbox("Skip our own employees", key="f_excl_own")
        st.text_input("Exclude companies", key="f_excl", placeholder="comma separated")
        st.slider("Shortlist size", 5, 50, key="f_size")
        go = st.form_submit_button("Find candidates", type="primary", width="stretch")
    st.markdown(
        '<div class="ts-note" style="margin-top:.8rem">Public professional profiles only. No contact details, salaries or '
        "personal data are collected (PDPL 151/2020). Nothing is sent to a candidate.</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------- header

st.markdown(
    '<div class="ts-hero"><div class="ts-kicker">Real estate talent sourcing</div>'
    "<h1>From hiring brief to a ranked, evidence-backed shortlist</h1>"
    "<p>Built for real estate companies, in-house recruiters and sourcing agencies in any market. "
    "Every score quotes its evidence, duplicates of past candidates are skipped, and a recruiter approves every contact.</p></div>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- run

if go:
    ss = st.session_state
    excl = lines(ss.f_excl) + ([ss.f_company] if ss.f_excl_own and ss.f_company else [])
    brief = HiringBrief(
        title=ss.f_title,
        location=ss.f_location,
        seniority=Seniority(ss.f_seniority),
        min_years=int(ss.f_years) or None,
        must_have=lines(ss.f_must),
        nice_to_have=lines(ss.f_nice),
        target_companies=list(dict.fromkeys(ss.f_devs + ss.f_brokers + lines(ss.f_other))),
        exclusions=excl,
        max_candidates=ss.f_size,
    )
    ss.thread = str(uuid.uuid4())
    for k in ("state", "final", "decisions"):
        ss.pop(k, None)
    steps(1)
    try:
        with st.status("Sourcing candidates. This takes about two minutes.", expanded=True) as status:
            bar = st.progress(0.0)
            done = 0
            for node in stream_stages(graph(), brief, ss.f_company, ss.thread):
                if node in STAGES:
                    done += 1
                    st.markdown(f":material/check: {STAGES[node]}")
                    bar.progress(done / len(STAGES))
            ss.state = snapshot(graph(), ss.thread)
            status.update(label="Shortlist ready for review", state="complete", expanded=False)
        st.rerun()
    except Exception as exc:
        st.error(f"The run stopped: {exc}. Try again, or widen the brief.")
        st.stop()

state = st.session_state.get("state")
final = st.session_state.get("final")

# ---------------------------------------------------------------- empty state

if not state:
    steps(0)
    cols = st.columns(3)
    how = [
        (
            "1. Describe the role",
            "Pick a template such as Sales Team Lead or Property Consultant, the area, and the developers or brokerages to source from.",
        ),
        (
            "2. Agent sources and scores",
            "It searches public profiles in English and Arabic, extracts professional facts, skips people you already have, and scores each one against a weighted rubric with quotes.",
        ),
        (
            "3. You decide",
            "Approve, edit or reject each candidate and their outreach draft. Export an Excel shortlist and an ATS import file. Nothing is sent automatically.",
        ),
    ]
    for col, (t, d) in zip(cols, how, strict=True):
        col.markdown(f'<div class="ts-how"><div class="ts-display">{t}</div><p>{d}</p></div>', unsafe_allow_html=True)
    st.write("")
    st.markdown('<div class="ts-note">Fill in the brief on the left and press <b>Find candidates</b>.</div>', unsafe_allow_html=True)
    st.stop()

crit: SearchCriteria = state["criteria"]
report = state["report"]
cands: list[ScoredCandidate] = state.get("candidates", [])

# ---------------------------------------------------------------- export page

if final:
    steps(3)
    fc = final["candidates"]
    chosen = [c for c in fc if c.status in ("approved", "edited")]
    cost = final["report"].token_cost_usd
    kpis(
        [
            ("Approved", len(chosen)),
            ("Rejected", sum(c.status == "rejected" for c in fc)),
            ("Undecided", sum(c.status == "pending" for c in fc)),
            ("Run saved as", f"#{final['run_id']}"),
            ("LLM cost", f"${cost:.4f}" if meter.priced else "not priced"),
        ]
    )
    d1, d2, d3 = st.columns([1, 1, 1])
    d1.download_button("Download shortlist (Excel)", final["excel"], "shortlist.xlsx", type="primary", width="stretch")
    d2.download_button("Download ATS import (CSV)", final["ats_csv"], "ats_import.csv", "text/csv", width="stretch")
    if d3.button("Start a new search", width="stretch"):
        for k in ("state", "final", "thread", "decisions"):
            st.session_state.pop(k, None)
        st.rerun()

    st.markdown("### Contact queue")
    st.caption("Approved candidates with their final message. Open the profile, copy the message, and send it from your own account.")
    if not chosen:
        st.markdown('<div class="ts-note">No candidates were approved in this run.</div>', unsafe_allow_html=True)
    for c in chosen:
        p = c.profile
        with st.container(border=True):
            meta = " · ".join(esc(x) for x in (p.current_title, p.company, p.city) if x)
            link = safe_url(p.profile_url)
            st.markdown(
                f'<div class="ts-name">{esc(p.name)}</div><div class="ts-meta">{meta}'
                + (f' · <a href="{esc(link)}" target="_blank" rel="noopener">Open public profile</a>' if link else "")
                + "</div>",
                unsafe_allow_html=True,
            )
            st.code(c.outreach_draft, language=None, wrap_lines=True)
    st.stop()

# ---------------------------------------------------------------- review page

steps(2)
decisions: dict[str, dict] = st.session_state.setdefault(
    "decisions", {c.profile.profile_url: {"status": "pending", "draft": c.outreach_draft} for c in cands}
)
checks = {c.profile.profile_url: must_have_check(crit, c) for c in cands}
meets = [c for c in cands if all(ok for _, ok in checks[c.profile.profile_url])]
kpis(
    [
        ("Search hits", report.hits),
        ("Profiles found", report.profiles_extracted),
        ("Already known, skipped", report.duplicates_removed),
        ("Shortlisted", report.shortlisted),
        ("Meet all must-haves", len(meets)),
    ]
)

tab_review, tab_strategy, tab_report = st.tabs(["Review candidates", "Search strategy", "Run report"])

with tab_strategy:
    a, b = st.columns([3, 2])
    with a:
        st.markdown("#### Scoring rubric")
        st.dataframe(
            pd.DataFrame(
                [{"Criterion": r.name, "Weight": r.weight, "Must-have": r.must_have, "What counts": r.description} for r in crit.rubric]
            ),
            hide_index=True,
            width="stretch",
        )
        st.markdown("#### Queries")
        st.dataframe(
            pd.DataFrame([{"Query": q.text, "Engine": q.engine, "Type": q.kind, "Language": q.language} for q in state["queries"]]),
            hide_index=True,
            width="stretch",
        )
    with b:
        st.markdown("#### Title variants")
        st.markdown(
            " ".join(f'<span class="chip">{esc(t)}</span>' for t in [crit.title, *crit.title_synonyms_en, *crit.title_synonyms_ar]),
            unsafe_allow_html=True,
        )
        st.markdown("#### Areas covered")
        st.markdown(
            " ".join(f'<span class="chip">{esc(t)}</span>' for t in crit.location_aliases or [crit.location]), unsafe_allow_html=True
        )
        st.markdown("#### Target companies")
        st.markdown(" ".join(f'<span class="chip">{esc(t)}</span>' for t in crit.target_companies) or "None", unsafe_allow_html=True)
        if crit.exclusions:
            st.markdown("#### Excluded")
            st.markdown(" ".join(f'<span class="chip miss">{esc(t)}</span>' for t in crit.exclusions), unsafe_allow_html=True)

with tab_report:
    kpis(
        [
            ("Pages read", report.pages_fetched),
            ("Search or fetch failures", report.fetch_failures),
            ("LLM provider", provider()),
            ("LLM cost so far", f"${meter.usd:.4f}" if meter.priced else "not priced"),
        ]
    )
    st.markdown("#### Sources")
    st.dataframe(pd.DataFrame([{"Source": k, "Hits": v} for k, v in report.sources.items()]), hide_index=True, width="stretch")
    st.caption("Failures are usually search timeouts or sites that block automated reading; the run continues without them.")

with tab_review:
    if not cands:
        st.warning("No candidates found. Free search may be rate-limited; try again in a minute, widen the area, or add a Tavily key.")
        st.stop()

    def approve_must_haves() -> None:
        for i, c in enumerate(cands):
            url = c.profile.profile_url
            if all(ok for _, ok in checks[url]) and decisions[url]["status"] == "pending":
                decisions[url]["status"] = "approved"
                st.session_state[f"s-{st.session_state.thread}-{i}"] = "approved"

    t1, t2, t3, t4 = st.columns([1.3, 1.3, 1.2, 1.2])
    view = t1.selectbox("Show", ["All candidates", "Meet all must-haves", "Undecided", "Approved", "Rejected"])
    min_fit = t2.slider("Minimum fit", 0, 100, 0, step=5)
    t3.write("")
    pending_ok = sum(1 for c in meets if decisions[c.profile.profile_url]["status"] == "pending")
    t3.button(f"Approve all that meet must-haves ({pending_ok})", on_click=approve_must_haves, disabled=not pending_ok, width="stretch")
    counts = {k: sum(d["status"] == k for d in decisions.values()) for k in DECISIONS}
    t4.markdown(
        f'<div class="ts-note" style="padding:.5rem .8rem">{counts["approved"]} approved · {counts["rejected"]} rejected · '
        f"{counts['pending']} undecided</div>",
        unsafe_allow_html=True,
    )

    shown = 0
    for i, c in enumerate(cands):
        p, url = c.profile, c.profile.profile_url
        d = decisions[url]
        ok_all = all(ok for _, ok in checks[url])
        if (
            (view == "Meet all must-haves" and not ok_all)
            or (view == "Undecided" and d["status"] != "pending")
            or (view == "Approved" and d["status"] != "approved")
            or (view == "Rejected" and d["status"] != "rejected")
            or c.fit_score * 100 < min_fit
        ):
            continue
        shown += 1
        tier_cls, tier_label = tier(checks[url], c.fit_score)
        meta = " · ".join(esc(x) for x in (p.current_title, p.company, p.city) if x) or "Title not listed"
        link = safe_url(url)
        chips = "".join(
            f'<span class="chip {"ok" if ok else "miss"}"><span class="g">{"✓" if ok else "✗"}</span> {esc(n)}</span>'
            for n, ok in checks[url]
        )
        if p.years_experience:
            chips += f'<span class="chip">{p.years_experience:g} years experience</span>'
        if p.source:
            chips += f'<span class="chip">via {esc(p.source)}</span>'
        with st.container(border=True):
            left, right = st.columns([3, 2], gap="large")
            with left:
                st.markdown(
                    f'<div class="ts-card-head"><div><div class="ts-name"><span class="ts-rank">{i + 1}.</span>{esc(p.name)}</div>'
                    f'<div class="ts-meta">{meta}'
                    + (f' · <a href="{esc(link)}" target="_blank" rel="noopener">Open public profile</a>' if link else "")
                    + f'</div><span class="tier {tier_cls}">{tier_label}</span></div>'
                    f'<div class="ts-fit"><div class="n">{round(c.fit_score * 100)}</div><div class="of">fit out of 100</div></div></div>'
                    f"<div>{chips}</div>",
                    unsafe_allow_html=True,
                )
                if p.achievements:
                    st.markdown("**Highlights:** " + "; ".join(esc(a) for a in p.achievements[:3]), unsafe_allow_html=True)
                with st.expander(f"Why this score: {len(c.criteria)} criteria with quoted evidence"):
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "Criterion": s.criterion,
                                    "Score": round(s.score * 100),
                                    "Evidence from the profile": s.evidence or "No evidence found",
                                }
                                for s in c.criteria
                            ]
                        ),
                        hide_index=True,
                        width="stretch",
                    )
                    st.caption(
                        f"Judge {round(c.judge_score * 100)} · text similarity {round(c.embedding_similarity * 100)}. "
                        "Quotes the source does not contain are marked [unverified] and count half."
                    )
            with right:
                dkey, skey = f"d-{st.session_state.thread}-{i}", f"s-{st.session_state.thread}-{i}"
                d["draft"] = st.text_area(
                    "Outreach draft (edit before approving)",
                    key=dkey,
                    height=170,
                    **({} if dkey in st.session_state else {"value": d["draft"]}),
                )
                d["status"] = st.radio(
                    "Decision",
                    DECISIONS,
                    key=skey,
                    horizontal=True,
                    format_func=DECISION_LABELS.get,
                    **({} if skey in st.session_state else {"index": DECISIONS.index(d["status"])}),
                )
    if not shown:
        st.markdown('<div class="ts-note">No candidates match this view.</div>', unsafe_allow_html=True)

    st.divider()
    n_ok = sum(dd["status"] == "approved" for dd in decisions.values())
    st.caption(
        "Finalizing saves decisions for future dedup and calibration, and builds the Excel and ATS files. Nothing is sent to candidates."
    )
    if st.button(f"Finalize shortlist ({n_ok} approved) and export", type="primary"):
        st.session_state.final = resume(graph(), st.session_state.thread, decisions)
        st.rerun()
