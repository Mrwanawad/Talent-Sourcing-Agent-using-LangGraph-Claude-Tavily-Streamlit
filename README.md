# Talent-Sourcing Agent

Hiring brief -> search strategy -> public professional profiles -> evidence-scored shortlist -> outreach drafts -> human approval -> Excel / ATS CSV. Design: [architecture.md](architecture.md). State: [CHECKPOINT.md](CHECKPOINT.md).

**LLM:** `LLM_PROVIDER=auto` uses Claude when `ANTHROPIC_API_KEY` is set, else Gemini (`gemini-3.1-flash-lite`, free tier throttled to `GEMINI_RPM=14`). Calls are batched, so a 20-candidate run is ~10 LLM calls and ~2 minutes.

## Pipeline (LangGraph, `talent_agent/graph.py`)

| Node | Module | Tools |
|---|---|---|
| parse | `brief_parser.py` | LLM structured output -> `SearchCriteria` + weighted rubric; Role + Location always enforced as must-haves (rule-based fallback) |
| plan | `query_planner.py` | boolean (Tavily) + semantic (Exa) queries, EN/AR title synonyms, location aliases, exclusions |
| research | `researcher.py` | Tavily, Exa, free DuckDuckGo fallback (`ddgs`), trafilatura, Playwright fallback; LinkedIn is never fetched (snippet only), login/authwall URLs skipped |
| extract | `extractor.py` | LLM -> `Profile` (professional fields only), up to 10 pages per call, PII scrubbed before the LLM sees text; rule fallback parses search titles, skips job ads |
| dedup | `dedup.py` | rapidfuzz vs ATS export + every previous run in the DB |
| score | `scoring.py` | bge-m3 similarity (optional) + LLM-as-judge per criterion with verbatim evidence, 6 candidates per call; unverified quotes halved; role/location also rule-scored (title fuzzy match, city aliases, LinkedIn country subdomain); failed must-have halves score; optional scikit-learn calibrator |
| outreach | `outreach.py` | personalized draft per candidate (8 per call), template fallback, never sent |
| approval | `graph.py` | `interrupt()`; recruiter approves / edits / rejects in the UI |
| export | `export.py`, `storage.py` | Excel (shortlist, search report, queries), ATS CSV (approved only), PostgreSQL/SQLite, Langfuse flush |

## Run

```bash
pip install -r requirements.txt   # or requirements-embeddings.txt for local bge-m3
playwright install chromium
cp .env.example .env          # add GEMINI_API_KEY or ANTHROPIC_API_KEY; TAVILY_API_KEY / EXA_API_KEY optional
streamlit run app.py
# headless
python run_cli.py examples/sales_team_lead_cairo.json --company Nawy --out out
```

Without keys every stage degrades to rules: DuckDuckGo search, title-based extraction, keyword/fuzzy judge, template outreach. A live run of the example brief with no keys returns ~14 real public profiles. Set `USE_DDG=false` to disable the free search.

## Quality

```bash
pytest -q            # 15 offline tests, includes end-to-end graph with interrupt/resume
ruff check .
python -m evals.run_evals extraction   # field accuracy on evals/data/labeled_profiles.jsonl
python -m evals.run_evals ranking      # acceptance rate, precision@10 from evals/data/decisions.csv
python -m evals.run_evals calibrate    # fit models/calibrator.pkl on manager decisions in the DB
```

## Deploy (Streamlit Community Cloud)

share.streamlit.io -> Create app -> this repo, branch `main`, file `app.py`, Python 3.12 (Advanced settings). Paste `.streamlit/secrets.toml.example` into Secrets with real values. `requirements.txt` has no torch/bge-m3 (`USE_EMBEDDINGS=false`; scoring uses token overlap + LLM judge) and no browser (`USE_PLAYWRIGHT=false`). Use a hosted PostgreSQL `DATABASE_URL` (Neon) so dedup memory survives restarts.

## Guardrails

- Professional fields only; emails/phones regex-scrubbed; no salary, personal-life or contact scraping (PDPL Law 151/2020).
- No logged-in scraping; official/recruiter APIs where terms require.
- Rubric and judge prompt exclude protected attributes.
- Nothing is contacted automatically; ATS CSV contains approved candidates only.

## Monitoring

Search report per run (hits, sources, fetch failures, duplicates, token cost) is stored in `runs.report` and the Excel "Search report" sheet. Langfuse traces every LLM call when `LANGFUSE_*` keys are set. Re-run `calibrate` periodically and compare score distribution vs. manager decisions for drift.
