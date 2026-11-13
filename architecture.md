# Talent-Sourcing Agent — Architecture

## Scenario
Leadership (CEO, CMO, sales directors) needs to hire for roles such as "Sales Team Lead, Cairo". Manual sourcing takes weeks. The agent turns a hiring brief into search strategies, finds public professional profiles in the target region, scores fit with evidence, drafts personalized outreach, and delivers a structured shortlist. A human approves every contact.

## Input
- Hiring brief: title, seniority, location, must-have skills, nice-to-haves, target companies, exclusions.
- Search sources: search APIs, public professional pages, official/recruiter APIs where terms require.
- Existing ATS candidates (to avoid duplicates).

## Output
- Shortlist (Excel / ATS CSV): name, current title, company, listed city, years of experience, relevant achievements, public profile URL, fit score, evidence per criterion, outreach draft, status.
- Search report: queries used, sources, coverage.

## Architecture

```
 Hiring brief (UI form)
        |
        v
 [Brief parser]  Claude -> structured criteria (Pydantic) + scoring rubric
        |
        v
 [Query planner]  boolean / semantic queries, title synonyms (Arabic + English)
        |
        v
 [Researcher]  Tavily / Exa -> Playwright for public pages
        |
        v
 [Profile extractor]  page -> professional fields only (Pydantic)
        |
        v
 [Dedup]  rapidfuzz vs. ATS and previous runs
        |
        v
 [Fit scoring]  bge-m3 embedding similarity (brief vs. profile)
                + LLM-as-judge rubric per criterion with evidence quotes
        |
        v
 [Outreach drafter]  personalized message per candidate
        |
        v
 [Human approval]  recruiter approves / edits / rejects
        |
        v
 [Export]  Excel + ATS CSV; Langfuse traces
```

## Tools Used
- Agents: Claude tool use, LangGraph
- Web: Tavily / Exa, Playwright, trafilatura
- Matching: bge-m3 (sentence-transformers), rapidfuzz
- Scoring: LLM-as-judge rubric, scikit-learn (calibration of combined score)
- Data & output: pandas, xlsxwriter, PostgreSQL
- UI: Streamlit
- Observability: Langfuse; quality: pytest, ruff

## Tools Not Used (and why)
- Salary guessing, personal-life or contact scraping: privacy law (PDPL Law 151/2020) and platform terms.
- Automatic outreach sending: human approval required.
- Logged-in scraping of professional networks: use official/recruiter APIs instead.

## Methodologies
- Shares the research-agent core with the Market & Lead Intelligence Agent.
- Evidence-grounded scoring (each criterion cites profile text).
- Bias check: rubric excludes protected attributes; score audit on samples.

## Evaluation Metrics
- Shortlist acceptance rate by hiring manager, precision@10.
- Extraction field accuracy on labeled profiles.
- Candidate response rate to outreach, time-to-shortlist.
- Cost per shortlist.

## Production Monitoring
- Source failure rate, empty results per brief.
- Score distribution vs. manager decisions (calibration drift).
- Token cost per run.

## Deployment Plan
- Streamlit Community Cloud (brief form, results table, Excel download).
- Agent runs on demand from UI; secrets in Streamlit secrets.
