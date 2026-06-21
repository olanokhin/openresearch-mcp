"""OpenResearch MCP server — zero-auth multi-source research tools."""

from __future__ import annotations

import asyncio
import os
import time
from importlib.metadata import version as _pkg_version

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
from openresearch_mcp.tools.github import read_repo
from openresearch_mcp.tools.web import read_pdf, read_url, web_search
from openresearch_mcp.tools.youtube import get_youtube_transcript

_READ_ONLY_WEB = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
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
        "accepts full URLs or bare 11-char video IDs.\n\n"
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


_PROBES: list[tuple[str, str]] = [
    ("duckduckgo",       "https://duckduckgo.com/?q=test&format=json"),
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


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    results = await asyncio.gather(*[_probe(n, u) for n, u in _PROBES])
    sources = dict(results)
    any_ok = any(v["status"] == "ok" for v in sources.values())
    all_ok = all(v["status"] == "ok" for v in sources.values())
    overall = "ok" if all_ok else ("degraded" if any_ok else "down")
    http_status = 200 if any_ok else 503
    return JSONResponse({"status": overall, "sources": sources}, status_code=http_status)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="OpenResearch MCP server")
    parser.add_argument("--port", type=int, default=None, help="Port to listen on (default: 8000)")
    parser.add_argument("--host", default=None, help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--stdio", action="store_true", help="Run in stdio mode (for Claude Desktop / Cursor)")
    args = parser.parse_args()

    # CLI args take precedence over env vars
    transport = "stdio" if args.stdio else os.getenv("MCP_TRANSPORT", "streamable-http")
    host = args.host or os.getenv("MCP_HOST", "0.0.0.0")
    port = args.port or int(os.getenv("MCP_PORT", "8000"))

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
