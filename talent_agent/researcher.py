"""Search APIs (Tavily, Exa, DuckDuckGo fallback) + public page fetch (trafilatura, Playwright fallback)."""

from __future__ import annotations

import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from talent_agent.config import get_settings
from talent_agent.models import SearchHit, SearchQuery, SearchReport
from talent_agent.observability import observe

log = logging.getLogger(__name__)

BLOCKED_PATHS = ("/login", "/signup", "/authwall", "/checkpoint")
# Pages behind a login wall: use the search snippet only, never fetch (platform terms, no logged-in scraping)
NO_FETCH_DOMAINS = ("linkedin.com",)


@observe(name="research.search")
def search(queries: list[SearchQuery], report: SearchReport) -> list[SearchHit]:
    s = get_settings()
    hits: list[SearchHit] = []
    for q in queries:
        try:
            if q.engine == "exa" and s.exa_api_key:
                hits += _exa(q, s.exa_api_key)
            elif s.tavily_api_key:
                hits += _tavily(q, s.tavily_api_key)
            elif q.kind == "boolean" and s.use_ddg:
                hits += _ddg(q, s.request_timeout)  # free fallback; semantic queries need Exa
        except Exception as exc:
            report.fetch_failures += 1
            log.warning("search failed [%s] %s: %s", q.engine if s.tavily_api_key or s.exa_api_key else "ddg", q.text[:60], exc)
    by_url: dict[str, SearchHit] = {}
    for h in hits:
        if not any(p in h.url for p in BLOCKED_PATHS):
            by_url.setdefault(h.url.split("?")[0].rstrip("/"), h)
    report.queries = queries
    report.hits = len(by_url)
    report.sources = dict(Counter(h.source for h in by_url.values()))
    return list(by_url.values())


def _tavily(q: SearchQuery, key: str) -> list[SearchHit]:
    from tavily import TavilyClient

    res = TavilyClient(api_key=key).search(q.text, max_results=10, search_depth="advanced", include_raw_content=True)
    return [
        SearchHit(
            url=r["url"],
            title=r.get("title", ""),
            snippet=r.get("content", ""),
            content=r.get("raw_content") or "",
            source="tavily",
            query=q.text,
        )
        for r in res.get("results", [])
    ]


def _exa(q: SearchQuery, key: str) -> list[SearchHit]:
    from exa_py import Exa

    res = Exa(api_key=key).search_and_contents(q.text, num_results=10, category="linkedin profile", text=True)
    return [
        SearchHit(url=r.url, title=r.title or "", snippet=(r.text or "")[:300], content=r.text or "", source="exa", query=q.text)
        for r in res.results
    ]


def _ddg(q: SearchQuery, timeout: int = 20) -> list[SearchHit]:
    from ddgs import DDGS

    try:
        rows = DDGS(timeout=timeout).text(q.text, max_results=10)
    except Exception as exc:  # ddgs raises on "No results found"
        if "no results" in str(exc).lower():
            return []
        raise
    return [
        SearchHit(url=r["href"], title=r.get("title", ""), snippet=r.get("body", ""), source="duckduckgo", query=q.text)
        for r in rows
        if r.get("href")
    ]


@observe(name="research.fetch")
def enrich(hits: list[SearchHit], report: SearchReport) -> list[SearchHit]:
    """Fill missing page text. Search APIs usually return content; fetch only what's empty."""
    s = get_settings()
    todo = [h for h in hits if len(h.content) < 300 and not any(d in h.url for d in NO_FETCH_DOMAINS)][: s.max_pages]
    with ThreadPoolExecutor(max_workers=6) as pool:
        texts = list(pool.map(lambda h: _fetch_text(h.url, s.request_timeout), todo))
    for h, text in zip(todo, texts, strict=True):
        if text:
            h.content = text
            report.pages_fetched += 1
        else:
            report.fetch_failures += 1
    if s.use_playwright:
        still_empty = [h for h in todo if len(h.content) < 300][:10]
        for h in still_empty:
            text = _playwright_text(h.url, s.request_timeout)
            if text:
                h.content = text
                report.pages_fetched += 1
    return [h for h in hits if h.content or h.snippet]


def _fetch_text(url: str, timeout: int) -> str:
    try:
        import trafilatura

        html = trafilatura.fetch_url(url)
        return (trafilatura.extract(html, include_comments=False) or "") if html else ""
    except Exception:
        return ""


def _playwright_text(url: str, timeout: int) -> str:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            html = page.content()
            browser.close()
        import trafilatura

        return trafilatura.extract(html) or ""
    except Exception as exc:
        log.debug("playwright failed %s: %s", url, exc)
        return ""
