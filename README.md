# openresearch-mcp

[![PyPI version](https://img.shields.io/pypi/v/openresearch-mcp)](https://pypi.org/project/openresearch-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/openresearch-mcp)](https://pypi.org/project/openresearch-mcp/)
[![License](https://img.shields.io/pypi/l/openresearch-mcp)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/olanokhin/openresearch-mcp/ci.yml?branch=main&label=CI)](https://github.com/olanokhin/openresearch-mcp/actions/workflows/ci.yml)
[![MCP Registry](https://img.shields.io/badge/MCP_Registry-listed-blue)](https://registry.modelcontextprotocol.io)

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
| `get_current_date` | Server clock | Current UTC date/time — anchors relative requests ("last 30 days") instead of guessing |
| `get_weather_forecast` | Open-Meteo | Current conditions + up to 16-day forecast by place name; no key. See licensing note below |
| `get_historical_weather` | Open-Meteo | Climate series since 1940 for a place + date range, aggregated monthly/yearly; no key. See licensing note below |
| `search_indicators` | World Bank | Find an indicator code by keyword ("GDP", "migration"); feed into `get_country_indicator` |
| `get_country_indicator` | World Bank | Yearly socio-economic series (GDP, population, inflation, migration, life expectancy…) by country + code; no key |
| `get_fx_rate` | Frankfurter (ECB) | Currency rates: latest, a historical date, or a date-range series (downsample week/month); no key |
| `get_crypto_price` | CoinGecko | Crypto price (current or daily history) by coin id/symbol vs a quote currency; no key |
| `search_news` | GDELT | Fresh global news on a topic (multilingual); returns articles to feed into `read_url`; no key (rate-limited ~1/5s) |
| `search_europepmc` | Europe PMC | Biomedical/life-science papers; flags open-access and gives a PDF URL to feed into `read_pdf`; no key |
| `search_bluesky_users` | Bluesky | Find researcher/dev profiles by name, handle, or bio; no key |
| `get_bluesky_profile` | Bluesky | Full bio + follower/post counts for a handle; no key |
| `read_bluesky_feed` | Bluesky | A user's recent original posts (reposts/replies filtered); no key |
| `get_company_financials` | SEC EDGAR | Annual revenue, earnings, assets for a US-listed company by ticker (10-K filings); no key (set `SEC_USER_AGENT` for heavy use) |

## Install

### From the MCP Registry (recommended for Claude Desktop / Cursor)

The server is listed on the [official MCP Registry](https://registry.modelcontextprotocol.io) as `io.github.olanokhin/openresearch-mcp`. Registry-aware clients can discover and install it without manual config — search for `openresearch-mcp` in your client's MCP browser.

### From PyPI

```bash
# Zero install, always isolated — recommended for manual use
uvx openresearch-mcp

# Or install globally
pip install openresearch-mcp
openresearch-mcp
```

By default the server starts on `http://127.0.0.1:8000/mcp` (Streamable HTTP, MCP 1.1+) — bound to loopback so it is not exposed to your local network. To expose it (e.g. in a container or behind a gateway), bind all interfaces explicitly:

```bash
# Custom port
uvx openresearch-mcp --port 9000

# Bind all interfaces (only behind an auth/rate-limit gateway)
uvx openresearch-mcp --host 0.0.0.0 --port 9000
```

> **Note:** when binding beyond loopback, put an auth/rate-limit gateway in front. The server is zero-auth by design, and `read_url`/`read_pdf` fetch arbitrary URLs (private/link-local/loopback ranges are blocked to prevent SSRF, but rate limiting is your responsibility).

## Update

```bash
# uvx
uvx --refresh openresearch-mcp

# pip
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
      "args": ["openresearch-mcp", "--stdio"]
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
      "args": ["openresearch-mcp", "--stdio"]
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
| `SEC_USER_AGENT` | Your contact (e.g. email) for SEC EDGAR fair-access; a default is used otherwise |

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
      "args": ["openresearch-mcp", "--stdio"],
      "env": {
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
- **Weather (Open-Meteo)**: data is licensed **[CC BY 4.0](https://open-meteo.com/en/license)** and free for **non-commercial** use up to ~10,000 requests/day. **Commercial use requires Open-Meteo's paid plan or self-hosting** — embedding `get_weather_forecast` in a commercial product without one inherits a license obligation. Attribution to Open-Meteo is required.
- **PDF parsing**: `read_pdf` parses untrusted PDFs in-process (with download-size and page caps). Fine for personal/low-volume use; a public high-volume deployment should isolate parsing in a subprocess with CPU/memory limits.

## Roadmap

- [ ] Reddit OAuth (browser-based, no user key management)
- [ ] GitHub Device Flow login
- [ ] PubMed / NCBI (optional key)
- [ ] NewsAPI support (optional key)

## Security

openresearch-mcp was reviewed and hardened using **[agent-security-skill](https://github.com/olanokhin/agent-security-skill)**,
an OWASP-aligned AI agent security review skill developed by the maintainer.

That review directly led to concrete hardening in this server: SSRF-resistant URL fetching,
untrusted-content framing for tool outputs, bounded downloads, pinned GitHub Actions,
dependency major-version caps, and regression tests for security-sensitive behavior.

See the hardening notes and current security posture in **[SECURITY.md](SECURITY.md)**.

## License

Apache 2.0

<!-- mcp-name: io.github.olanokhin/openresearch-mcp -->
