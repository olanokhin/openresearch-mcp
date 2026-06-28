# openresearch-mcp — Expansion Roadmap

Planned tools grouped by research domain. All sources verified live unless marked otherwise.

## Project principle

OpenResearch is **free for research use and works zero-auth out of the box** — the server boots and does useful work with no key, no registration, no config. That is the promise (and the Post 1 hook: *Nothing to register. Nothing to leak. Nothing to configure.*).

Zero-auth is the **default**, not the *only* mode. Optional keys may extend the server — but they are always **additive**: any key only widens limits or unlocks extra functions; **no key is ever required for base functionality.** Hiding genuinely-available data behind "it's my principle" would be a disservice to the researcher the project exists for.

## Auth tiers

One symbol = one meaning. The symbol encodes the **threat-model / access nature**, never the topic.

- **✅ zero-auth** — works out of the box, no key. The core.
- **⚙️ service data-token (free)** — optional free key (email signup, no card) to a *data service*; reads public data under a higher quota, raises limits or unlocks functions. The server works fully without it. Safe, encouraged. (e.g. OpenAlex email, GitHub PAT, CoinGecko demo, Alpha Vantage stock key.)
- **📊 regulated data (free token)** — same *access nature* as ⚙️ (a data-token, not account login), but the **data itself is licensed/regulated** so no keyless provider exists (e.g. intraday equity prices). Free token, instant signup, no card. Separated only so the user knows *why* a key is needed here — it is **not** an account-level credential.
- **🔑 personal-auth** — a genuinely different class: a credential that authenticates **as the user's own account** (e.g. Bluesky app-password for post search). Grants access *under the user's identity*. Must be isolated, clearly labelled, opt-in, and never silently bundled with data-tokens.

**The line that matters (security):** ⚙️ and 📊 are *data-tokens* — they read public data under a quota, they do **not** log in as anyone. 🔑 is the only tier where the user hands over account-level access. The 📊/⚙️ split is about *why the key exists* (regulated data vs. just limits); the 🔑 boundary is about *what the key is* (account credential). Don't let 🔑 ever mean "sensitive topic" — it means "logs in as you".

## Shared conventions for every new tool

- Fixed trusted host → no `safe_get`/SSRF needed.
- All external content wrapped via `format_untrusted(source, body)`.
- Clamp `max_results` / date ranges.
- Gracefully handle non-JSON / `error`-field responses instead of raising.
- **`@tool_safe` catches transport, not shape or input — guard both.** `@tool_safe` only catches `SourceError` (network/HTTP/non-JSON). *Anything else* sails past it and crashes the tool, from two directions: (1) **parsing the source response** — a `KeyError`/`IndexError` on a malformed-but-200 body; never do bare `r["key"]` / `seq[i]`, use `.get()` with skip/fallback or a safe-index helper (`_at`), and drop rows missing required fields; (2) **coercing input params** — a `ValueError`/`TypeError` from `int(days)` / date parsing when a client passes junk; wrap coercion in `try/except` and return a friendly `"Invalid …"`. *(Caught four times in 0.2.0 — weather `IndexError`, two World Bank `KeyError`s, crypto `int(days)` — before it was a rule. Write new tools with it from the start.)*
- **Rate-limit guard, server-side — not a prompt.** Where a source enforces a hard limit (GDELT: 1 req / 5 s), the server owns a TTL cache + throttle. An agent *will* loop; tool-description warnings don't stop it. Treat source rate-limits as a server responsibility, not an instruction.
- **Identifier contract (chaining gate).** Every tool accepts/returns shared identifier formats so outputs chain into inputs without translation: country = ISO-3166 alpha-2; dates = ISO-8601 (`YYYY-MM-DD`); currency/crypto = standard codes (`USD`, `EUR`, `bitcoin`/`btc`); location = `name` **or** `lat,lon`; ticker = as-is. This is a **release gate for 0.2.0 tools**, not a later cleanup — fix it before many tools ship, or each invents its own format and chaining stays in the README instead of the code.

**Free-key acquisition** is noted in each tool's row.

---

## Already shipped (v0.1.x core)

| Tool | Source | Auth | Free-key note |
| ---- | ------ | ---- | ------------- |
| `web_search` | DuckDuckGo (ddgs) | ✅ | — |
| `read_url` | Any webpage (SSRF-safe) | ✅ | — |
| `read_pdf` | Any PDF / arXiv | ✅ | — |
| `search_openalex` | OpenAlex (250M+ works, all disciplines) | ⚙️ | `OPENALEX_EMAIL` — any email, no registration, joins polite pool |
| `search_hacker_news` | HN via Algolia | ✅ | — |
| `search_stackoverflow` | Stack Overflow | ⚙️ | `STACKEXCHANGE_KEY` — free at stackapps.com, no card, higher daily quota |
| `read_repo` | GitHub public repos | ⚙️ | `GITHUB_TOKEN` — free PAT in GitHub settings, 60→5,000 req/hr |
| `get_youtube_transcript` | YouTube captions | ✅ | — |

---

## Domain: Core / Utility

Zero-auth, no external call — server-generated helpers that make the rest of the stack usable.

| Tool | Params | Description | Source / Endpoint | Auth | Status | Notes |
| ---- | ------ | ----------- | ----------------- | ---- | ------ | ----- |
| `get_current_date` | — | Current UTC date/time + weekday, so the agent anchors relative requests instead of guessing | server clock (`datetime.now(UTC)`) | ✅ | Shipped (0.1.9) | **Host-agnostic date anchor.** The model can't reliably know "today" and the host isn't guaranteed to inject it; static server `instructions` would freeze the date at boot. Trusted output → **not** wrapped via `format_untrusted`. No timezone/time-of-day knobs until a tool needs them. Landed early in 0.1.9 (alongside the infra refactor) so the 0.2.0 date-driven tools can rely on it from day one. |

> **Composability rule (date-driven tools):** every tool that takes a date range defaults `end` → today via `identifiers.today_iso()`, so the agent usually supplies only `start`. `get_current_date` covers the remaining case — when the agent must *reason* about an absolute date, not just pass one. The two together mean relative-date requests never depend on the model guessing the clock.

---

## Domain: Social

| Tool | Params | Description | Source / Endpoint | Auth | Status | Notes |
| ---- | ------ | ----------- | ----------------- | ---- | ------ | ----- |
| `search_bluesky_users` | `query` | Find researcher/dev profiles by name, handle, or bio text | Bluesky `app.bsky.actor.searchActors` | ✅ | **Built (0.2.0-dev)** | Public AppView (`public.api.bsky.app`), zero-auth; returns handle, displayName, bio. |
| `read_bluesky_feed` | `handle`, `limit?` | Read a user's recent posts ("what did they write") | Bluesky `app.bsky.feed.getAuthorFeed` | ✅ | **Built (0.2.0-dev)** | Server `filter=posts_no_replies` + client drop of reposts (`reason`); defensive nested parse; live-confirmed original-posts-only. |
| `get_bluesky_profile` | `handle` | Full bio, links, follower counts | Bluesky `app.bsky.actor.getProfile` | ✅ | **Built (0.2.0-dev)** | Cheap context before a feed; counts formatted; `@` stripped from handle. |
| `search_bluesky_posts` | `query`, `max_results?` | Keyword search across all public posts | Bluesky `app.bsky.feed.searchPosts` | 🔑 | 0.4 / personal-auth | **Requires user's own Bluesky app-password** (`BLUESKY_IDENTIFIER` + `BLUESKY_APP_PASSWORD`) — authenticates *as the user's account*, not a data-token. Distinct threat-model: isolate, label clearly, opt-in only. Tool description must tell the agent: works only if app-password set, else suggest the user add one to unlock post search. |

> **Scope for the agent (in tool descriptions):** zero-auth tools find people and read their public feeds. Keyword post-search across the network needs the user's own Bluesky app-password → exposed as `search_bluesky_posts` (🔑 personal-auth). The agent should: use the zero-auth tools by default; if the user explicitly wants network-wide post search, tell them it requires adding their Bluesky app-password, and why that's a different (account-level) credential than the other optional keys.

---

## Domain: News / Trends

| Tool | Params | Description | Source / Endpoint | Auth | Status | Notes |
| ---- | ------ | ----------- | ----------------- | ---- | ------ | ----- |
| `search_news` | `query`, `max_results?` | Fresh global news on a topic, multilingual (English query → 65 languages) | GDELT DOC 2.0 `mode=ArtList` | ✅ | **Built (0.2.0-dev)** | Returns title/URL/domain/country/language/date → feed to `read_url`. **Validates the throttle path**: `min_interval=5`, `cache_ttl=300`; 429 + plain-text body → graceful "rate-limited, retry" (live-confirmed, multilingual results). |
| `news_trend` | `query`, `timespan?` | Volume-of-mentions curve over time (Google-Trends substitute for media) | GDELT `mode=TimelineVol` | ✅ | Planned | — |

> **Rate limit (critical):** GDELT allows ~1 request / 5 sec. On breach it returns **plain text, not JSON** → tool must detect non-JSON and return "rate limited, retry", never crash. **Server owns a TTL cache + throttle (see Shared conventions) — do not rely on agent-side warnings to honour the 1 req / 5 s limit.**

---

## Domain: Finance — markets & fundamentals

> **This domain is mostly zero-auth.** Fundamentals (SEC), crypto (CoinGecko), and FX (Frankfurter) need no key at all. Only one category — **intraday/daily prices of regulated equities** — requires a key, and even that is a *free* key, because regulated market data has no reliable keyless provider. So the domain delivers real research value out of the box; the key only unlocks one optional slice.

| Tool | Params | Description | Source / Endpoint | Auth | Status | Notes |
| ---- | ------ | ----------- | ----------------- | ---- | ------ | ----- |
| `get_company_financials` | `ticker` | Annual/quarterly revenue, earnings, fundamentals | SEC EDGAR XBRL `companyconcept` + `company_tickers.json` (ticker→CIK) | ✅ | **Built (0.2.0-dev)** | ticker→CIK via cached ticker map; per-concept fetch with revenue-tag fallback + local `SourceError` catch (missing concept skips, not aborts); dedupe by fiscal year; 10-K only. **SEC 403s a URL-only UA** → default UA carries a contact; set `SEC_USER_AGENT` for heavy use. US filers only. |
| `search_sec_filings` | `query`, `max_results?` | Find 10-K/10-Q/8-K filings by company/topic | SEC EDGAR full-text `efts.sec.gov` | ✅ | **0.2.0 if verified** | Domain entry point (find before fetch). Promote to 0.2.0 **once the full-text endpoint is confirmed with a live curl** — else stays 0.3 rather than ship unverified in the "all verified live" wave. |
| `get_company_market_cap` | `ticker` | Annual share count / market cap point (yearly price proxy) | SEC EDGAR XBRL (`EntityCommonStockSharesOutstanding`, 10-K market section) | ✅ | Planned | US filers only; yearly granularity from filings |
| `get_crypto_price` | `coin`, `vs=usd\|btc`, `days?` | Coin price in USD or vs BTC; current + daily history | CoinGecko keyless `coins/{id}/market_chart` & `simple/price` | ✅ | **Built (0.2.0-dev)** | **First consumer of the throttle/cache path** (`fetch_json` `min_interval=1.5`, `cache_ttl=30`) → keyless 429s absorbed; inline symbol→id map (crypto ≠ fiat, stays out of `normalize_currency`); unknown coin = `{}`@200 handled; daily downsample; live test green. ⚙️ optional free CoinGecko **Demo key** → `COINGECKO_DEMO_KEY` is a 0.3.0 add. |
| `get_fx_rate` | `base`, `symbols`, `start?`, `end?`, `group?` | Currency rates: latest, historical, time series (day/week/month) since 1999 | Frankfurter `api.frankfurter.dev` (ECB) | ✅ | **Built (0.2.0-dev)** | **First consumer of `normalize_currency`** (base + each symbol); 3 modes (latest/point/series); `group` downsampling is **client-side** (API has none); output capped; live test green. |
| `get_stock_history` | `ticker`, `interval=daily\|weekly\|monthly`, `start?`, `end?` | Stock price OHLCV time series (equities/ETFs) | Alpha Vantage / EODHD | 📊 | 0.4 / regulated | **Regulated data, free token.** Equity price data is licensed — no keyless source exists (Stooq blocked: JS-challenge + quota). Works with a **free service data-token**: Alpha Vantage (alphavantage.co/support — instant, no card, 25 calls/day) → `ALPHAVANTAGE_KEY`, or EODHD demo (eodhd.com — 20 calls/day) → `EODHD_API_KEY`. Returns "requires a free optional key — see README" if unset. This is a *data-token*, **not** an account credential — the 📊 marks regulated data, not account-level access. |

> README framing: *Stock **fundamentals** (revenue, earnings), **crypto** (daily, USD/BTC), and **FX** are zero-auth — usable out of the box. Intraday/daily **stock-price series** need a key (a free one), because regulated equity market data has no keyless provider in 2026. This is the **regulated** tier, not a gap in the design: the rest of the finance-econ domain works with no key at all.*

---

## Domain: Socio-economics / Macro

| Tool | Params | Description | Source / Endpoint | Auth | Status | Notes |
| ---- | ------ | ----------- | ----------------- | ---- | ------ | ----- |
| `get_country_indicator` | `country`, `indicator`, `start?`, `end?` | Yearly series: GDP, population, inflation, net migration, life expectancy, etc. | World Bank `v2/country/{c}/indicator/{i}` | ✅ | **Built (0.2.0-dev)** | Handles WB's `[meta, rows]` array + HTTP-200 error payloads; filters `value: null`; consumes `normalize_country` (→alpha-2) + `normalize_year`; orders oldest→newest; capped at `MAX_TEXT_CHARS`; live test green. |
| `search_indicators` | `query` | Find World Bank indicator code by keyword ("GDP", "migration") | World Bank indicator catalog | ✅ | **Built (0.2.0-dev)** | Searches the **WDI set (source=2, ~1,500 indicators)** — full 29k catalog is too big to sweep per query. One cached request (`cache_ttl=3600`), client-side token-AND filter; ships *with* `get_country_indicator`. live test green. |

---

## Domain: Climate / Weather

| Tool | Params | Description | Source / Endpoint | Auth | Status | Notes |
| ---- | ------ | ----------- | ----------------- | ---- | ------ | ----- |
| `get_weather_forecast` | `location`, `days?` | Current + up to 16-day forecast | Open-Meteo `api.open-meteo.com/v1/forecast` | ✅ | **Built (0.2.0-dev)** | Host `api.`; `timezone=auto`; WMO codes → human text; live integration test green. `past_days` not wired yet (kept minimal). |
| `get_historical_weather` | `location`, `start`, `end`, `aggregate=monthly\|yearly` | Climate series since 1940 (ERA5) for trends/anomalies | Open-Meteo `archive-api.open-meteo.com/v1/archive` | ✅ | **Built (0.2.0-dev)** | Host `archive-api.`; aggregates daily→monthly/yearly (temp→mean, precip→sum, nulls skipped); reuses `_geocode` + `normalize_date_range`; output capped at `MAX_TEXT_CHARS`; live integration test green. |
| `_geocode` (internal) | `name` | City name → lat/lon + timezone | Open-Meteo `geocoding-api.open-meteo.com/v1/search` | ✅ | **Built (0.2.0-dev)** | Helper, not a standalone tool; shipped with `get_weather_forecast`. |

> ⚠️ **License — must be in README (trust issue, not a footnote).** Open-Meteo data is **CC BY 4.0, free for *non-commercial* use** up to ~10k req/day. A user who embeds openresearch-mcp in a **commercial product inherits a license violation for this tool unless they move to Open-Meteo's paid plan or self-host.** State this plainly so commercial users aren't caught unaware. Attribution required. Also catch `{"error": true, "reason": ...}` responses.

---

## Domain: Science — biomed depth & DOI canon

> OpenAlex already covers **all disciplines** (physics, chem, neuro, etc.). These add depth/full-text, not breadth.

| Tool | Params | Description | Source / Endpoint | Auth | Status | Notes |
| ---- | ------ | ----------- | ----------------- | ---- | ------ | ----- |
| `search_pubmed` | `query`, `max_results?` | Biomedical/neuro/medical search with MeSH | NCBI E-utilities `esearch`/`esummary` | ⚙️ | Verified live | Works keyless; free **NCBI API key** (ncbi.nlm.nih.gov/account — instant, no card) → `NCBI_API_KEY` raises 3→10 req/sec |
| `search_europepmc` | `query`, `max_results?` | Biomed + OA full-text discovery | Europe PMC `webservices/rest/search` | ✅ | **Built (0.2.0-dev)** | **OA→read_pdf gate (first real chaining link in the wave)**: OA papers surface a PDF URL for `read_pdf`; paywalled withhold it. Defensive nested parse of `fullTextUrlList`; live-confirmed. |
| `get_crossref` | `doi` | Canonical metadata for any publisher's DOI (Nature, Science, Cell…) | Crossref `api.crossref.org/works/{doi}` | ⚙️ | Planned | No key; just set `mailto` (any email) to join the faster polite pool → `CROSSREF_MAILTO` |

---

## Release waves (semver)

`0.1.x` was patch-level: bug fixes + four-pass security hardening → patch releases. **0.1.9** is the seam: it lands the shared infrastructure for the expansion (`http` transport, `identifiers` gate, `constants`, ruff/mypy/CI) plus one zero-auth core utility (`get_current_date`) — no *domain* tools, so still a patch. New domains start at 0.2.0 as backward-compatible additions → **minor bumps.** Each wave is its own release and its own announcement; don't block a release waiting for all domains.

### 0.2.0 — zero-auth domain expansion (first wave)
All ✅, all verified live, no keys. Ships the "grew from academic tool into a cross-domain research stack" story. Identifier contract (above) is a release gate for every tool here.
`get_historical_weather` + `get_weather_forecast` · `get_company_financials` · `get_crypto_price` · `get_fx_rate` · `get_country_indicator` + `search_indicators` · `search_europepmc` · social core (`search_bluesky_users` + `read_bluesky_feed` + `get_bluesky_profile`) · `search_news` · `search_sec_filings` (*if curl-verified*)

### 0.3.0 — service data-tokens (⚙️ only — the safe, encouraged wave)
One clean message: *optional free data-tokens that only raise limits / add depth — no account access, ever.* Keeping this wave ⚙️-pure means the "free key, totally safe" story isn't muddied by account-level concerns.
`search_pubmed` (NCBI) · `get_crossref` · `get_company_market_cap` · CoinGecko demo-key path · `news_trend`

### 0.4.0 — regulated data & personal-auth (📊 / 🔑 — the opt-in trust wave)
Separated deliberately: this is the "account-level / regulated" conversation, and it deserves its own announcement so it doesn't dilute the ⚙️ message in 0.3.0.
- **📊 regulated data (free token, not account login):** `get_stock_history` (Alpha Vantage / EODHD)
- **🔑 personal-auth (logs in as the user):** `search_bluesky_posts` (Bluesky app-password) — isolated, clearly labelled, opt-in

> Framing arc: 0.2.0 = "works out of the box, zero-auth." 0.3.0 = "optional free data-tokens go further — still no account access." 0.4.0 = "two opt-in cases: regulated data via a free token, and one account-level credential — here's exactly what each is, so you choose knowingly." Each message *reinforces* the previous instead of undercutting it.

---

## After expansion: freeze coverage, build the layer

Six domains is a complete research stack. Further domains = diminishing returns. Next phase is **quality, not breadth**:

1. **Composability** — the identifier contract is already a 0.2.0 release gate (see Shared conventions), so outputs chain into inputs from the first tool. This phase adds the *output→input wiring* on top: documented chains (search → read_url/read_pdf), and verifying real multi-hop flows end-to-end rather than per-tool.
2. **Server `instructions`** — embed 2-3 hop recipes so the bare MCP is useful without a skill (handles short chains).
3. **`openresearch-skill`** — long-horizon / deep-research orchestration: planning, cross-domain triangulation, proactive *relevant* context enrichment (as hypotheses, with caveats on correlation), citation discipline. Activates semantically on research-style tasks; a soft amplifier, never a hard dependency.
4. **Plugin (Claude Code)** — bundle MCP + skill into one `/plugin install`; elsewhere they remain separately usable.

---

## Cross-domain triangulation (where the value lives)

The point isn't N tools — it's that they **chain**:

- **Company econ profile:** `get_company_financials` → `get_company_market_cap` → `search_news` (by ticker) → `search_openalex` (topic)
- **Country socio-econ profile:** `get_country_indicator` (GDP, migration) → `get_historical_weather` (climate) → `search_news` (source-country) → `search_openalex`
- **Live discourse on a paper:** `search_openalex` (find authors) → `search_bluesky_users` → `read_bluesky_feed`
- **Trend-to-content (blogger):** `news_trend` (rising curve) → HN/Bluesky (independent voices) → World Bank/SEC (unused data layer = unique angle)
