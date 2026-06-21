"""Academic and developer community search tools — all free tier, no keys required."""

from __future__ import annotations

import os

import requests
from bs4 import BeautifulSoup

from openresearch_mcp.formatting import format_untrusted


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
    body = "\n\n".join(lines)
    return format_untrusted("Hacker News", body) if body else "No results found."


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
    out = "\n\n".join(lines)
    return format_untrusted("Stack Overflow", out) if out else "No results found."


def _reconstruct_abstract(inv_idx: dict | None) -> str:
    """Reconstruct plain text from OpenAlex abstract_inverted_index format."""
    if not inv_idx:
        return ""
    length = max(pos for positions in inv_idx.values() for pos in positions) + 1
    words: list[str] = [""] * length
    for word, positions in inv_idx.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words)


def search_openalex(query: str, max_results: int = 5) -> str:
    """Search OpenAlex for academic papers, books, and datasets. 250M+ works, no API key required.

    Set OPENALEX_EMAIL env var to join the polite pool for higher rate limits.

    Args:
        query: Search query string.
        max_results: Number of works to return (1–10, default 5).
    """
    max_results = max(1, min(max_results, 10))
    email = os.getenv("OPENALEX_EMAIL", "")
    user_agent = f"openresearch-mcp (mailto:{email})" if email else "openresearch-mcp"

    r = requests.get(
        "https://api.openalex.org/works",
        params={
            "search": query,
            "per_page": max_results,
            "select": "title,doi,publication_year,open_access,authorships,abstract_inverted_index,primary_location",
        },
        headers={"User-Agent": user_agent},
        timeout=15,
    )
    r.raise_for_status()
    works = r.json().get("results", [])
    lines = []
    for work in works:
        authors = ", ".join(
            a.get("author", {}).get("display_name", "")
            for a in (work.get("authorships") or [])[:3]
        )
        oa = work.get("open_access") or {}
        pdf_url = oa.get("oa_url")
        location = work.get("primary_location") or {}
        url = location.get("landing_page_url") or work.get("doi") or ""
        abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))

        entry = (
            f"{work.get('title', 'Untitled')} ({work.get('publication_year') or 'N/A'})\n"
            f"Authors: {authors}\nURL: {url}"
        )
        if pdf_url:
            entry += f"\nPDF: {pdf_url}"
        if abstract:
            entry += f"\nAbstract: {abstract[:600]}"
        lines.append(entry)
    body = "\n\n".join(lines)
    return format_untrusted("OpenAlex", body) if body else "No results found."
