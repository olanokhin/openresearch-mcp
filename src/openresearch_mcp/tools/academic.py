"""Academic and developer community search tools — all free tier, no keys required."""

from __future__ import annotations

import os

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS


def search_hacker_news(query: str, max_results: int = 10) -> str:
    """Search Hacker News stories and discussions via Algolia API. No API key required.

    Args:
        query: Search query string.
        max_results: Number of stories to return (1–20, default 10).
    """
    max_results = max(1, min(max_results, 20))
    r = requests.get(
        "https://hn.algolia.com/api/v1/search",
        params={"query": query, "tags": "story", "hitsPerPage": max_results},
        timeout=10,
    )
    r.raise_for_status()
    hits = r.json().get("hits", [])
    lines = []
    for hit in hits:
        hn_url = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        lines.append(
            f"{hit.get('title', 'Untitled')}\n"
            f"HN: {hn_url}\nURL: {hit.get('url', hn_url)}\n"
            f"Points: {hit.get('points', 0)} | Comments: {hit.get('num_comments', 0)}"
        )
    return "\n\n".join(lines) or "No results found."


def search_stackoverflow(query: str, max_results: int = 5) -> str:
    """Search Stack Overflow for questions and answers. No API key required (throttled without key).

    Args:
        query: Search query string.
        max_results: Number of questions to return (1–10, default 5).
    """
    max_results = max(1, min(max_results, 10))
    params: dict = {
        "order": "desc",
        "sort": "votes",
        "q": query,
        "site": "stackoverflow",
        "pagesize": max_results,
        "filter": "withbody",
    }
    key = os.getenv("STACKEXCHANGE_KEY")
    if key:
        params["key"] = key
    r = requests.get("https://api.stackexchange.com/2.3/search/advanced", params=params, timeout=15)
    r.raise_for_status()
    items = r.json().get("items", [])
    lines = []
    for item in items:
        body = BeautifulSoup(item.get("body", ""), "html.parser").get_text()[:400]
        lines.append(
            f"{item.get('title', 'Untitled')}\n{item.get('link', '')}\n"
            f"Score: {item.get('score', 0)} | Answers: {item.get('answer_count', 0)}\n{body}"
        )
    return "\n\n".join(lines) or "No results found."


def search_semantic_scholar(query: str, max_results: int = 5) -> str:
    """Search Semantic Scholar for academic papers with abstracts and open-access PDFs.

    No API key required (100 req/5min). Set SEMANTIC_SCHOLAR_KEY env var for higher limits.
    Falls back to DuckDuckGo snippet search on 429.

    Args:
        query: Search query string.
        max_results: Number of papers to return (1–10, default 5).
    """
    max_results = max(1, min(max_results, 10))
    headers = {}
    key = os.getenv("SEMANTIC_SCHOLAR_KEY")
    if key:
        headers["x-api-key"] = key

    try:
        r = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": query, "fields": "title,abstract,year,url,openAccessPdf,authors", "limit": max_results},
            headers=headers,
            timeout=15,
        )
        r.raise_for_status()
        papers = r.json().get("data", [])
        lines = []
        for paper in papers:
            authors = ", ".join(a.get("name", "") for a in (paper.get("authors") or [])[:3])
            pdf_info = paper.get("openAccessPdf")
            pdf_url = pdf_info.get("url") if pdf_info else None
            entry = (
                f"{paper.get('title', 'Untitled')} ({paper.get('year') or 'N/A'})\n"
                f"Authors: {authors}\nURL: {paper.get('url', '')}"
            )
            if pdf_url:
                entry += f"\nPDF: {pdf_url}"
            entry += f"\nAbstract: {(paper.get('abstract') or 'No abstract.')[:600]}"
            lines.append(entry)
        return "\n\n".join(lines) or "No results found."
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 429:
            with DDGS() as ddgs:
                results = list(ddgs.text(f"site:semanticscholar.org {query}", max_results=max_results))
            if not results:
                return "Semantic Scholar rate limited. Try again in a few minutes."
            return "\n\n".join(f"{r.get('title')}\n{r.get('href')}\n{r.get('body')}" for r in results)
        raise
