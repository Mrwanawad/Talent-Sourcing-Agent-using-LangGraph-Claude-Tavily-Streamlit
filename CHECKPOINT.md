# Checkpoint — Talent-Sourcing Agent

_Last updated: 2026-11-13_

## Status: DONE and LIVE on Streamlit Community Cloud

- App: https://talent-sourcing-agent-using-langgraph-claude-tavily-app-wmyt3y.streamlit.app
- First cloud run (2026-11-13): 17 hits, 10 profiles, 2 duplicates removed against Neon, 8 shortlisted, 7 fetch failures.

- Repo: https://github.com/Mrwanawad/Talent-Sourcing-Agent-using-LangGraph-Claude-Tavily-Streamlit
- Commits authored by Mrwan Awad only, no Claude attribution.
- Project #4 in `../projects-overview.md`. Design: [architecture.md](architecture.md). Usage: [README.md](README.md).
- LLM: Gemini `gemini-3.1-flash-lite` (free tier, key in `.env` as `GEMINI_API_KEY`). Claude is still supported and wins when `ANTHROPIC_API_KEY` is set (`LLM_PROVIDER=auto`). No Anthropic key available.
- Search: DuckDuckGo (free). Tavily/Exa used automatically if keys are added.
- DB: Neon project `Nawy-Talent-Sourcing-Agent` (id `still-fire-15428922`, aws-eu-central-1, org `org-restless-pond-36388009`), URL in `.env` `DATABASE_URL`.
- `.streamlit/secrets.toml` (gitignored) already holds the real values to paste into Streamlit Cloud.

## Checkpoints

| # | Checkpoint | State |
|---|---|---|
| 1 | Architecture (`architecture.md`) | done |
| 2 | Pydantic models, settings (.env + Streamlit secrets) | done |
| 3 | Brief parser: LLM structured output -> criteria + weighted rubric; Role + Location always enforced; rule fallback | done |
| 4 | Query planner: boolean (site:, EN/AR synonyms, location aliases, exclusions) + semantic (Exa) | done |
| 5 | Researcher: Tavily, Exa, DuckDuckGo fallback, trafilatura, Playwright fallback; LinkedIn never fetched | done |
| 6 | Extractor: LLM batched (10 pages/call), PII scrub, professional fields only; heuristic title parser | done |
| 7 | Dedup: rapidfuzz vs ATS CSV/Excel + previous runs in DB | done |
| 8 | Scoring: optional bge-m3 + batched LLM judge (6/call) with verbatim evidence, unverified quotes halved, role/location rule-scored too, must-have halving, logistic calibrator | done |
| 9 | Outreach drafts, batched (8/call), template fallback, never sent | done |
| 10 | LangGraph graph with `interrupt()` approval, resume | done |
| 11 | Export: Excel + ATS CSV; SQLite / Neon Postgres storage | done |
| 12 | Langfuse tracing (keys from .env/secrets) | done, no keys set |
| 13 | Streamlit UI + headless CLI (UTF-8 console) | done |
| 14 | LLM providers: Claude (forced tool use) + Gemini (JSON schema), RPM throttle, 429/503/timeout retry | done |
| 15 | Tests (15 offline) + ruff | done, green |
| 16 | Evals: extraction, ranking, calibrate | done |
| 17 | CI (`.github/workflows/ci.yml`) | pushed, see repo Actions |
| 18 | Git repo + GitHub push (public) | done |
| 19 | Streamlit Community Cloud deploy | done (live URL above) |

## Latest results

- `pytest -q`: 15 passed. `ruff check .` + `ruff format --check .`: clean.
- Extraction eval (rule fallback): name/title/company/city 1.0 on 10 synthetic labeled pages.
- Live run, Gemini + DuckDuckGo + Neon, `examples/sales_team_lead_cairo.json`: 18 hits, 17 profiles, ~2 min, no 429s. Top 4: Egypt real-estate sales leads (Coldwell Banker Egypt x2, G Developments, Emaar Misr). Gulf/other-country profiles rank lower. Run saved to Neon, so the next run with the same brief dedups these people.
- Before batching: ~100 LLM calls, 6 min, free-tier 429s. After: ~10 calls.

## Deploy steps (Streamlit Community Cloud)

1. share.streamlit.io -> sign in with GitHub -> Create app -> repo above, branch `main`, main file `app.py`.
2. Advanced settings: Python 3.12. Secrets: paste the contents of local `.streamlit/secrets.toml`.
3. Deploy. First build ~3-5 min (no torch). Test with the default form.

## Known issues / gotchas

- Token cost shows $0: `gemini-3.1-flash-lite` has no price in `llm.PRICING`. Set `LLM_PRICE_IN` / `LLM_PRICE_OUT` (USD per 1M tokens) to report it.
- Gemini free tier: 15 requests/min; `GEMINI_RPM=14` throttles. A second user running at the same time shares the quota.
- DuckDuckGo occasionally times out on a query (Yahoo/Mojeek backends); the run continues. Results from Streamlit Cloud IPs may be noisier; a Tavily key fixes this.
- LinkedIn is snippet-only (no fetch), so skills/achievements are thin and the judge scores many criteria 0. Scores are relative, not absolute.
- `.env` key had been put in `EXA_API_KEY`; it was moved to `GEMINI_API_KEY`.
- Eval data is synthetic; real precision@10 needs manager decisions then `python -m evals.run_evals calibrate`.
- bge-m3 moved to `requirements-embeddings.txt` (local only); `USE_EMBEDDINGS` defaults to false.

## Next steps

1. Check the 7 cloud fetch failures (likely DuckDuckGo timeouts or sites blocking Streamlit IPs); a Tavily key removes both.
2. Optional: Tavily key for better search; Langfuse keys for traces; Gemini price env vars for cost.
3. Collect approve/reject decisions from real runs, then `calibrate`.
