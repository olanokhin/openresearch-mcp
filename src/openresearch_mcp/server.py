"""OpenResearch MCP server — zero-auth multi-source research tools."""

from __future__ import annotations

import asyncio
import os
import time
from importlib.metadata import version as _pkg_version
from typing import Any

import requests as _requests
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse

from openresearch_mcp.tools.academic import (
    search_hacker_news,
    search_openalex,
    search_stackoverflow,
)
from openresearch_mcp.tools.bluesky import (
    get_bluesky_profile,
    read_bluesky_feed,
    search_bluesky_users,
)
from openresearch_mcp.tools.core import get_current_date
from openresearch_mcp.tools.crypto import get_crypto_price
from openresearch_mcp.tools.europepmc import search_europepmc
from openresearch_mcp.tools.fx import get_fx_rate
from openresearch_mcp.tools.github import read_repo
from openresearch_mcp.tools.news import search_news
from openresearch_mcp.tools.sec import get_company_financials, search_sec_filings
from openresearch_mcp.tools.weather import get_historical_weather, get_weather_forecast
from openresearch_mcp.tools.web import read_pdf, read_url, web_search
from openresearch_mcp.tools.worldbank import get_country_indicator, search_indicators
from openresearch_mcp.tools.youtube import get_youtube_transcript

_READ_ONLY_WEB = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

# Local, server-generated tools (no external call). Value changes over time, so
# not idempotent; closed-world since nothing is fetched.
_READ_ONLY_LOCAL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)

mcp = FastMCP(
    name="openresearch-mcp",
    version=_pkg_version("openresearch-mcp"),
    instructions=(
        "Zero-auth multi-source research server. All tools are read-only and call external services — "
        "no API keys required out of the box.\n\n"
        "Tool selection guide:\n"
        "• web_search — broad discovery; best for recent events, news, or topics not in academic databases. "
        "Powered by DuckDuckGo.\n"
        "• read_url — fetch the full text of a specific webpage once you already have a URL.\n"
        "• read_pdf — extract text from any PDF or arXiv paper; accepts /abs/, /pdf/, and /html/ arXiv URLs "
        "interchangeably.\n"
        "• search_openalex — preferred for academic papers, books, and datasets; 250M+ works via OpenAlex, "
        "zero rate limiting on free tier. Set OPENALEX_EMAIL for the polite pool.\n"
        "• search_hacker_news — tech community discussion, startup news, engineering war stories.\n"
        "• search_stackoverflow — programming Q&A; use when looking for code solutions or error messages.\n"
        "• read_repo — explore a public GitHub repository: returns metadata, README, file tree, and key "
        "config/doc files. Accepts owner/repo shorthand or full GitHub URL.\n"
        "• get_youtube_transcript — fetch captions from a YouTube video for summarization or citation; "
        "accepts full URLs or bare 11-char video IDs.\n"
        "• get_current_date — the current UTC date/time. Call this to anchor any relative request "
        "(\"last 30 days\", \"since last year\", \"recent\") instead of guessing today's date.\n"
        "• get_weather_forecast — current conditions + up to 16-day daily forecast for a place by name; "
        "no key needed (Open-Meteo).\n"
        "• get_historical_weather — past climate series (since 1940) for a place + date range, aggregated "
        "monthly or yearly for trend/anomaly analysis; no key needed (Open-Meteo). Use get_current_date to "
        "anchor relative ranges.\n"
        "• search_indicators — find a World Bank indicator code by keyword (\"GDP\", \"migration\"); feed the "
        "code into get_country_indicator.\n"
        "• get_country_indicator — yearly socio-economic series (GDP, population, inflation, migration, life "
        "expectancy…) for a country + indicator code; no key needed (World Bank).\n"
        "• get_fx_rate — currency exchange rates (ECB): latest, a historical date, or a date-range series "
        "(downsample week/month); no key needed (Frankfurter).\n"
        "• get_crypto_price — cryptocurrency price (current or daily history) by coin id/symbol vs a quote "
        "currency; no key needed (CoinGecko, keyless tier is rate-limited).\n"
        "• search_news — fresh global news on a topic (multilingual) via GDELT; returns articles to feed "
        "into read_url. Rate-limited to ~1 call / 5 s — don't loop; it returns a retry message if tripped.\n"
        "• search_europepmc — biomedical / life-science literature; flags open-access papers and gives a PDF "
        "URL to feed into read_pdf. Complements search_openalex (which covers all disciplines).\n"
        "• search_bluesky_users — find researcher/dev Bluesky profiles by name, handle, or bio.\n"
        "• get_bluesky_profile — full bio + follower/post counts for a handle (cheap context before a feed).\n"
        "• read_bluesky_feed — a user's recent original posts (reposts/replies filtered). Chain: "
        "search_openalex → search_bluesky_users → read_bluesky_feed to see live discourse from paper authors.\n"
        "• get_company_financials — annual revenue, earnings, and assets for a US-listed company by ticker, "
        "from SEC 10-K filings; no key (set SEC_USER_AGENT to your email to comply with SEC fair-access).\n"
        "• search_sec_filings — full-text search of SEC EDGAR filings (10-K/10-Q/8-K) by keyword/company; "
        "returns a document URL to feed into read_url or read_pdf.\n\n"
        "Optional env vars to increase rate limits: GITHUB_TOKEN (60→5k req/hr), "
        "OPENALEX_EMAIL (polite pool, higher limits), STACKEXCHANGE_KEY (higher SO quota)."
    ),
)

mcp.tool(
    title="Web Search",
    tags={"search", "web"},
    annotations=_READ_ONLY_WEB,
)(web_search)

mcp.tool(
    title="Read Web Page",
    tags={"web", "content"},
    annotations=_READ_ONLY_WEB,
)(read_url)

mcp.tool(
    title="Read PDF",
    tags={"web", "content", "academic"},
    annotations=_READ_ONLY_WEB,
)(read_pdf)

mcp.tool(
    title="Read GitHub Repository",
    tags={"github", "code"},
    annotations=_READ_ONLY_WEB,
)(read_repo)

mcp.tool(
    title="Search Hacker News",
    tags={"search", "community"},
    annotations=_READ_ONLY_WEB,
)(search_hacker_news)

mcp.tool(
    title="Search Stack Overflow",
    tags={"search", "community", "code"},
    annotations=_READ_ONLY_WEB,
)(search_stackoverflow)

mcp.tool(
    title="Search OpenAlex",
    tags={"search", "academic"},
    annotations=_READ_ONLY_WEB,
)(search_openalex)

mcp.tool(
    title="Get YouTube Transcript",
    tags={"content", "video"},
    annotations=_READ_ONLY_WEB,
)(get_youtube_transcript)

mcp.tool(
    title="Get Current Date",
    tags={"utility", "time"},
    annotations=_READ_ONLY_LOCAL,
)(get_current_date)

mcp.tool(
    title="Get Weather Forecast",
    tags={"weather", "climate"},
    annotations=_READ_ONLY_WEB,
)(get_weather_forecast)

mcp.tool(
    title="Get Historical Weather",
    tags={"weather", "climate"},
    annotations=_READ_ONLY_WEB,
)(get_historical_weather)

mcp.tool(
    title="Search World Bank Indicators",
    tags={"search", "economics", "macro"},
    annotations=_READ_ONLY_WEB,
)(search_indicators)

mcp.tool(
    title="Get Country Indicator",
    tags={"economics", "macro"},
    annotations=_READ_ONLY_WEB,
)(get_country_indicator)

mcp.tool(
    title="Get FX Rate",
    tags={"finance", "currency"},
    annotations=_READ_ONLY_WEB,
)(get_fx_rate)

mcp.tool(
    title="Get Crypto Price",
    tags={"finance", "crypto"},
    annotations=_READ_ONLY_WEB,
)(get_crypto_price)

mcp.tool(
    title="Search News",
    tags={"search", "news"},
    annotations=_READ_ONLY_WEB,
)(search_news)

mcp.tool(
    title="Search Europe PMC",
    tags={"search", "academic", "biomed"},
    annotations=_READ_ONLY_WEB,
)(search_europepmc)

mcp.tool(
    title="Search Bluesky Users",
    tags={"search", "social"},
    annotations=_READ_ONLY_WEB,
)(search_bluesky_users)

mcp.tool(
    title="Get Bluesky Profile",
    tags={"social"},
    annotations=_READ_ONLY_WEB,
)(get_bluesky_profile)

mcp.tool(
    title="Read Bluesky Feed",
    tags={"social", "content"},
    annotations=_READ_ONLY_WEB,
)(read_bluesky_feed)

mcp.tool(
    title="Get Company Financials",
    tags={"finance", "economics"},
    annotations=_READ_ONLY_WEB,
)(get_company_financials)

mcp.tool(
    title="Search SEC Filings",
    tags={"search", "finance"},
    annotations=_READ_ONLY_WEB,
)(search_sec_filings)


# Deliberately a *representative sample* of upstream reachability, NOT a per-tool
# availability matrix. We don't add a probe for every new tool/source — that list
# would balloon and each /health hit would fan out N outbound requests (the very
# amplification the TTL cache below guards against). New domains (weather, finance,
# …) intentionally do not get their own probe; /health answers "are core upstreams
# reachable from here", not "is every tool up". Tool failures surface per-call via
# the graceful SourceError contract instead.
_PROBES: list[tuple[str, str]] = [
    ("duckduckgo",       "https://lite.duckduckgo.com/lite/"),
    ("github",           "https://api.github.com/rate_limit"),
    ("hacker_news",      "https://hn.algolia.com/api/v1/search?query=test&hitsPerPage=1"),
    ("stackoverflow",    "https://api.stackexchange.com/2.3/info?site=stackoverflow"),
    ("openalex",         "https://api.openalex.org/works?search=test&per_page=1&select=id"),
    ("youtube",          "https://www.youtube.com"),
]

_PROBE_HEADERS = {"User-Agent": "openresearch-mcp/healthcheck"}


async def _probe(name: str, url: str) -> tuple[str, dict]:
    start = time.monotonic()
    try:
        resp = await asyncio.to_thread(
            _requests.get, url, timeout=5, headers=_PROBE_HEADERS, allow_redirects=True
        )
        ms = round((time.monotonic() - start) * 1000)
        # 429 means the service is up but rate-limiting us — report as reachable
        if resp.status_code == 429:
            return name, {"status": "ok", "note": "rate_limited", "latency_ms": ms}
        resp.raise_for_status()
        return name, {"status": "ok", "latency_ms": ms}
    except Exception as exc:
        ms = round((time.monotonic() - start) * 1000)
        return name, {"status": "error", "error": str(exc)[:120], "latency_ms": ms}


_HEALTH_TTL = 10.0  # seconds — cap outbound-probe amplification from unauthenticated /health
_health_cache: dict[str, Any] = {"at": 0.0, "payload": None, "status": 503}
_health_lock = asyncio.Lock()


async def _compute_health() -> tuple[dict, int]:
    results = await asyncio.gather(*[_probe(n, u) for n, u in _PROBES])
    sources = dict(results)
    any_ok = any(v["status"] == "ok" for v in sources.values())
    all_ok = all(v["status"] == "ok" for v in sources.values())
    overall = "ok" if all_ok else ("degraded" if any_ok else "down")
    return {"status": overall, "sources": sources}, (200 if any_ok else 503)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    now = time.monotonic()
    # Serve a cached result so repeated/unauthenticated hits don't fan out 6 probes each.
    if _health_cache["payload"] is not None and (now - _health_cache["at"]) < _HEALTH_TTL:
        return JSONResponse(_health_cache["payload"], status_code=_health_cache["status"])
    async with _health_lock:
        now = time.monotonic()
        if _health_cache["payload"] is None or (now - _health_cache["at"]) >= _HEALTH_TTL:
            payload, status = await _compute_health()
            _health_cache.update(at=time.monotonic(), payload=payload, status=status)
    return JSONResponse(_health_cache["payload"], status_code=_health_cache["status"])


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="OpenResearch MCP server")
    parser.add_argument("--port", type=int, default=None, help="Port to listen on (default: 8000)")
    parser.add_argument("--host", default=None, help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--stdio", action="store_true", help="Run in stdio mode (for Claude Desktop / Cursor)")
    args = parser.parse_args()

    # CLI args take precedence over env vars
    transport = "stdio" if args.stdio else os.getenv("MCP_TRANSPORT", "streamable-http")
    # Default to loopback so a local `uvx openresearch-mcp` is not exposed to the LAN.
    # Containers/public deployments opt in explicitly via MCP_HOST=0.0.0.0 (see Dockerfile).
    host = args.host or os.getenv("MCP_HOST", "127.0.0.1")
    port = args.port or int(os.getenv("MCP_PORT", "8000"))

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
