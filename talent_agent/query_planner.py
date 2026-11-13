"""Criteria -> boolean (Tavily) and semantic (Exa) queries in English and Arabic."""

from __future__ import annotations

from talent_agent.models import SearchCriteria, SearchQuery

# Public professional pages only. No logged-in scraping.
PROFILE_SITES = ["linkedin.com/in", "wuzzuf.net", "bayt.com", "about.me"]


def plan_queries(c: SearchCriteria, max_queries: int = 12) -> list[SearchQuery]:
    titles = list(dict.fromkeys([c.title.split(",")[0].strip(), *c.title_synonyms_en]))[:4]
    places = (c.location_aliases or [c.location])[:3]
    skills = c.skills[:3]
    excl = " ".join(f'-"{e}"' for e in c.exclusions[:3])
    queries: list[SearchQuery] = []

    for site in PROFILE_SITES[:2]:
        title_or = " OR ".join(f'"{t}"' for t in titles)
        place_or = " OR ".join(f'"{p}"' for p in places)
        queries.append(SearchQuery(text=f"site:{site} ({title_or}) ({place_or}) {excl}".strip(), engine="tavily"))

    for company in c.target_companies[:4]:
        queries.append(SearchQuery(text=f'site:linkedin.com/in "{titles[0]}" "{company}" "{places[0]}"', engine="tavily"))

    for ar in c.title_synonyms_ar[:2]:
        queries.append(SearchQuery(text=f'"{ar}" "{places[-1]}" site:linkedin.com/in', engine="tavily", language="ar"))

    skill_txt = ", ".join(skills) if skills else "a strong track record"
    queries.append(
        SearchQuery(
            text=f"Profile of a {c.seniority.value} {titles[0]} based in {places[0]} with experience in {skill_txt}",
            kind="semantic",
            engine="exa",
        )
    )
    if c.target_companies:
        queries.append(
            SearchQuery(
                text=f"{titles[0]} who worked at {', '.join(c.target_companies[:3])} in {places[0]}",
                kind="semantic",
                engine="exa",
            )
        )

    seen: set[str] = set()
    unique = [q for q in queries if not (q.text in seen or seen.add(q.text))]
    return unique[:max_queries]
