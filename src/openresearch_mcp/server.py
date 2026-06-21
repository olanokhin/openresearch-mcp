"""OpenResearch MCP server — zero-auth multi-source research tools."""

from __future__ import annotations

import os

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from openresearch_mcp.tools.academic import (
    search_hacker_news,
    search_semantic_scholar,
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
    instructions=(
        "Zero-auth multi-source research server. All tools are read-only and call external services — "
        "no API keys required out of the box.\n\n"
        "Tool selection guide:\n"
        "• web_search — broad discovery; best for recent events, news, or topics not in academic databases. "
        "Powered by DuckDuckGo.\n"
        "• read_url — fetch the full text of a specific webpage once you already have a URL.\n"
        "• read_pdf — extract text from any PDF or arXiv paper; accepts /abs/, /pdf/, and /html/ arXiv URLs "
        "interchangeably.\n"
        "• search_semantic_scholar — preferred for academic papers, abstracts, citations, and open-access PDFs; "
        "auto-falls back to DuckDuckGo snippets on 429.\n"
        "• search_hacker_news — tech community discussion, startup news, engineering war stories.\n"
        "• search_stackoverflow — programming Q&A; use when looking for code solutions or error messages.\n"
        "• read_repo — explore a public GitHub repository: returns metadata, README, file tree, and key "
        "config/doc files. Accepts owner/repo shorthand or full GitHub URL.\n"
        "• get_youtube_transcript — fetch captions from a YouTube video for summarization or citation; "
        "accepts full URLs or bare 11-char video IDs.\n\n"
        "Optional env vars to increase rate limits: GITHUB_TOKEN (60→5k req/hr), "
        "SEMANTIC_SCHOLAR_KEY (100 req/5min→1 req/sec), STACKEXCHANGE_KEY (higher SO quota)."
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
    title="Search Semantic Scholar",
    tags={"search", "academic"},
    annotations=_READ_ONLY_WEB,
)(search_semantic_scholar)

mcp.tool(
    title="Get YouTube Transcript",
    tags={"content", "video"},
    annotations=_READ_ONLY_WEB,
)(get_youtube_transcript)


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "streamable-http")
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8000"))

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
