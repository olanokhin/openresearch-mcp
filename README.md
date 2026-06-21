# openresearch-mcp

[![PyPI version](https://img.shields.io/pypi/v/openresearch-mcp)](https://pypi.org/project/openresearch-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/openresearch-mcp)](https://pypi.org/project/openresearch-mcp/)
[![License](https://img.shields.io/pypi/l/openresearch-mcp)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/olanokhin/openresearch-mcp/ci.yml?branch=main&label=CI)](https://github.com/olanokhin/openresearch-mcp/actions/workflows/ci.yml)

Zero-auth multi-source research MCP server. Works with Claude Desktop, Cursor, OpenCode, Open WebUI, or any MCP-compatible agent — no API keys required.

## Tools

| Tool | Source | Notes |
| ---- | ------ | ----- |
| `web_search` | DuckDuckGo | Optional `site=` param to scope to a domain (e.g. `arxiv.org`) |
| `read_url` | Any webpage | Strips nav/scripts, returns clean text |
| `read_pdf` | Any PDF or arXiv | Accepts `/abs/`, `/pdf/`, `/html/` arXiv URLs interchangeably |
| `search_openalex` | OpenAlex | 250M+ works, zero rate limiting; set `OPENALEX_EMAIL` for polite pool |
| `search_hacker_news` | HN via Algolia | Story search with points + comment counts |
| `search_stackoverflow` | Stack Overflow API | Set `STACKEXCHANGE_KEY` for higher quota |
| `read_repo` | GitHub public repos | README + file tree + key docs; set `GITHUB_TOKEN` for 5k req/hr |
| `get_youtube_transcript` | YouTube captions | Accepts full URLs, `youtu.be/` links, shorts, or bare video IDs |

## Install

```bash
# Recommended — zero install, always isolated
uvx openresearch-mcp

# Or install globally with pip
pip install openresearch-mcp
openresearch-mcp
```

By default the server starts on `http://0.0.0.0:8000/mcp` (Streamable HTTP, MCP 1.1+).

## Update

```bash
uvx --refresh openresearch-mcp
```

With pip:

```bash
pip install --upgrade openresearch-mcp
```

## Connect to an MCP client

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`  
(Windows: `%APPDATA%\Claude\claude_desktop_config.json`)

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

Restart Claude Desktop after saving. The server runs in stdio mode — no port needed.

### Cursor

Create or edit `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (per-project):

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

### HTTP agents (OpenCode, Open WebUI, custom)

Start the server:

```bash
uvx openresearch-mcp
# or: openresearch-mcp
```

Point your agent at:

```text
http://localhost:8000/mcp
```

## Optional env vars

All tools work without any keys. Set these to increase rate limits:

| Variable | Effect |
| -------- | ------ |
| `GITHUB_TOKEN` | GitHub: 60 → 5,000 req/hr |
| `OPENALEX_EMAIL` | OpenAlex polite pool (higher limits) |
| `STACKEXCHANGE_KEY` | Stack Overflow: higher daily quota |

Example with keys:

```bash
GITHUB_TOKEN=ghp_... OPENALEX_EMAIL=you@example.com uvx openresearch-mcp
```

Or in Claude Desktop config:

```json
{
  "mcpServers": {
    "openresearch": {
      "command": "uvx",
      "args": ["openresearch-mcp"],
      "env": {
        "MCP_TRANSPORT": "stdio",
        "GITHUB_TOKEN": "ghp_...",
        "OPENALEX_EMAIL": "you@example.com"
      }
    }
  }
}
```

## Health check

When running in HTTP mode, check which sources are reachable:

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "sources": {
    "duckduckgo":    { "status": "ok", "latency_ms": 173 },
    "github":        { "status": "ok", "latency_ms": 101 },
    "hacker_news":   { "status": "ok", "latency_ms": 308 },
    "stackoverflow": { "status": "ok", "latency_ms": 247 },
    "openalex":      { "status": "ok", "latency_ms": 412 },
    "youtube":       { "status": "ok", "latency_ms": 320 }
  }
}
```

`status` is `"ok"`, `"degraded"` (some sources down), or `"down"` (all unreachable). HTTP 200 / 503.

## Known limitations

- **Reddit / Zenodo**: block unauthenticated scraping — not included
- **YouTube**: rate-limited at scale; works well for personal/low-volume use

## Roadmap

- [ ] Reddit OAuth (browser-based, no user key management)
- [ ] GitHub Device Flow login
- [ ] PubMed / NCBI (optional key)
- [ ] NewsAPI support (optional key)

## License

MIT
