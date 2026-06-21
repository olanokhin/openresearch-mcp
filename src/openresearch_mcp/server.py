"""OpenResearch MCP server — zero-auth multi-source research tools."""

from __future__ import annotations

import os

from fastmcp import FastMCP

from openresearch_mcp.tools.academic import (
    search_hacker_news,
    search_semantic_scholar,
    search_stackoverflow,
)
from openresearch_mcp.tools.github import read_repo
from openresearch_mcp.tools.web import read_pdf, read_url, web_search
from openresearch_mcp.tools.youtube import get_youtube_transcript

mcp = FastMCP(
    name="openresearch-mcp",
    instructions=(
        "Multi-source research server. All tools work without API keys. "
        "Optional env vars unlock higher rate limits or additional sources: "
        "GITHUB_TOKEN, SEMANTIC_SCHOLAR_KEY, STACKEXCHANGE_KEY."
    ),
)

# Register all tools
mcp.tool()(web_search)
mcp.tool()(read_url)
mcp.tool()(read_pdf)
mcp.tool()(read_repo)
mcp.tool()(search_hacker_news)
mcp.tool()(search_stackoverflow)
mcp.tool()(search_semantic_scholar)
mcp.tool()(get_youtube_transcript)


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "streamable-http")
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8000"))

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    main()
