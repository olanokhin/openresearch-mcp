# openresearch-mcp

Zero-auth multi-source research MCP server. Works with Claude Desktop, Cursor, OpenCode, Open WebUI, or any MCP-compatible agent — no API keys required.

## Tools

| Tool | Source | Auth |
|------|--------|------|
| `web_search` | DuckDuckGo | None |
| `read_url` | Any webpage | None |
| `read_pdf` | Any PDF / arXiv | None |
| `read_repo` | GitHub public repos | None (set `GITHUB_TOKEN` for 5k req/hr) |
| `search_hacker_news` | HN via Algolia API | None |
| `search_stackoverflow` | Stack Overflow API | None (set `STACKEXCHANGE_KEY` for higher limits) |
| `search_semantic_scholar` | Semantic Scholar API | None (set `SEMANTIC_SCHOLAR_KEY` for 1 req/sec) |
| `get_youtube_transcript` | YouTube captions | None |

## Quickstart

### Docker (recommended)

```bash
docker run -p 8000:8000 ghcr.io/yourusername/openresearch-mcp
```

With optional keys for higher limits:

```bash
docker run -p 8000:8000 \
  -e GITHUB_TOKEN=ghp_... \
  -e SEMANTIC_SCHOLAR_KEY=... \
  ghcr.io/yourusername/openresearch-mcp
```

### Local

```bash
pip install openresearch-mcp
openresearch-mcp
```

Or with uv:

```bash
uvx openresearch-mcp
```

### stdio (for Claude Desktop / Cursor)

```bash
MCP_TRANSPORT=stdio openresearch-mcp
```

Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "openresearch": {
      "command": "uvx",
      "args": ["openresearch-mcp"],
      "env": { "MCP_TRANSPORT": "stdio" }
    }
  }
}
```

## Connect via HTTP

Point your agent at `http://localhost:8000/mcp` (Streamable HTTP transport, MCP 1.1+).

## Known limitations

- **Reddit / Zenodo**: block unauthenticated requests — not included in v1
- **YouTube**: rate-limited by YouTube at scale; works for personal use
- **Semantic Scholar**: 100 req/5min without key; auto-falls back to DDG snippets on 429

## Roadmap

- [ ] Reddit OAuth (browser-based, no user key management)
- [ ] GitHub Device Flow login
- [ ] OpenAlex (zero-auth, 250M+ papers)
- [ ] NewsAPI support (optional key)
- [ ] PubMed / NCBI (optional key)

## License

MIT
