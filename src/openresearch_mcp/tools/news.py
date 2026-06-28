"""Global news search via GDELT DOC 2.0 — zero-auth, no API key.

GDELT indexes worldwide news in 65+ languages; an English query matches translated
coverage. The keyless endpoint enforces ~1 request / 5 s and, when tripped, returns
HTTP 429 with a *plain-text* body (not JSON). Both are absorbed by the shared
transport: ``min_interval`` spaces calls, the 429/non-JSON paths surface a graceful
"rate-limited, retry" instead of crashing, and ``cache_ttl`` lets a looping agent
re-ask without re-hitting the source.
"""

from __future__ import annotations

from typing import Any

from openresearch_mcp.constants import MAX_TEXT_CHARS
from openresearch_mcp.formatting import format_untrusted
from openresearch_mcp.http import fetch_json, tool_safe

_GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
# Hard source limit is 1 req / 5 s → space live calls; cache briefly so re-asks are free.
_MIN_INTERVAL = 5.0
_CACHE_TTL = 300.0


def _fmt_date(seendate: Any) -> str:
    """GDELT 'seendate' is like '20260628T120000Z' → 'YYYY-MM-DD HH:MM'. Defensive."""
    s = str(seendate or "")
    if len(s) >= 13 and s[8] == "T":
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]} {s[9:11]}:{s[11:13]}"
    return s


@tool_safe
def search_news(query: str, max_results: int = 10) -> str:
    """Search fresh global news on a topic (multilingual). No API key required.

    Returns recent articles (title, URL, domain, country, language, date) → feed a
    URL into read_url for the full text. Powered by GDELT.

    Args:
        query: Topic to search, e.g. "renewable energy" or "central bank rates".
        max_results: Number of articles to return (1–50, default 10).
    """
    if not query or not query.strip():
        return "Provide a search topic, e.g. 'renewable energy'."
    try:
        n = max(1, min(int(max_results), 50))
    except (TypeError, ValueError):
        return f"Invalid max_results {max_results!r}; provide a whole number (1–50)."

    data = fetch_json(
        _GDELT,
        source="GDELT",
        params={
            "query": query.strip(),
            "mode": "ArtList",
            "format": "json",
            "maxrecords": n,
            "sort": "DateDesc",
        },
        timeout=30,
        min_interval=_MIN_INTERVAL,
        cache_ttl=_CACHE_TTL,
    )

    raw = data.get("articles") if isinstance(data, dict) else None
    # Filter to well-formed rows up front so the header count matches what's rendered.
    articles = [a for a in raw if isinstance(a, dict)] if isinstance(raw, list) else []
    if not articles:
        return f"No recent news found for {query!r}."

    lines = [f'News for "{query.strip()}" ({len(articles)} articles):']
    for art in articles:
        meta = " · ".join(
            str(x) for x in (
                art.get("domain"),
                art.get("sourcecountry"),
                art.get("language"),
                _fmt_date(art.get("seendate")),
            ) if x
        )
        lines.append(
            f"\n{art.get('title') or 'Untitled'}\n{art.get('url') or ''}\n{meta}"
        )

    return format_untrusted("news", "\n".join(lines)[:MAX_TEXT_CHARS])
