# Security Policy and Hardening Report

**openresearch-mcp** is a zero-auth MCP server. Strong controls around external data
fetching and tool outputs are therefore a top priority — the tools fetch
attacker-influenceable content and, in HTTP mode, expose a network service.

## Affected Versions

PyPI releases are immutable, so earlier versions remain installable and **still contain
the pre-hardening code**. Pin accordingly.

| Version range | Status |
|---------------|--------|
| `< 0.1.6`     | **Vulnerable** — unvalidated URL fetching (SSRF), unbounded downloads, no untrusted-content framing. Do not use. |
| `0.1.6`       | Core hardening present (SSRF validation, framing, byte caps, loopback default). Missing some defense-in-depth (IPv4-mapped / NAT64 blocking). Upgrade recommended. |
| `0.1.7`–`0.1.9` | **Fully hardened** core (8 tools). `0.1.9` adds the shared `http` transport (single error contract, throttle, bounded cache). |
| `>= 0.2.0`    | **Fully hardened + cross-domain expansion.** 13 new zero-auth fixed-host tools (weather, finance, macro, news, biomed, social, SEC filings). OWASP-reviewed as a wave: no CRITICAL/HIGH; framing extended to error paths, log-newline scrubbing, URL path-segment encoding. Recommended. |

Always install the latest:

```bash
uvx openresearch-mcp                 # always isolated, latest
pip install -U openresearch-mcp      # or upgrade in place
```

---

## Security Hardening Journey

The project was reviewed and hardened using
**[agent-security-skill](https://github.com/olanokhin/agent-security-skill)**, an
OWASP-aligned AI agent security review skill developed by the maintainer.

This was not a generic checklist pass: findings were applied directly to
openresearch-mcp and resulted in concrete code, dependency, workflow, and test changes.
Each pass was cross-checked with an independent model to reduce single-reviewer blind spots.

### Summary

- **Before review:** several high-impact AI-agent security gaps — SSRF exposure, raw
  external content returned to agents, and unbounded fetch/parsing paths.
- **As of `>= 0.1.7`:** no known CRITICAL or HIGH findings remain *within the reviewed
  scope*. Remaining items are defense-in-depth or operational controls.

**Current version:** v0.2.0 — the core SSRF/framing hardening (`>= 0.1.7`) is unchanged.
This wave adds 13 new **fixed-host, zero-auth** tools; because their hosts are trusted and
hardcoded (not attacker-controlled), they deliberately do **not** use `safefetch` — the SSRF
threat model is unchanged. The wave had its own OWASP pass: **no CRITICAL/HIGH**, and the
MEDIUM/LOW findings (unframed external error fields, log-newline injection, unencoded URL
path segments) were fixed before release (see v0.2.0 below).

---

### Review Timeline

Independent cross-model review across four passes (two reviewers, alternating), driving
findings from CRITICAL to none:

| Pass     | Reviewer | Outcome                    | Representative findings |
|----------|----------|----------------------------|-------------------------|
| Pass 1   | GPT      | Multiple CRITICAL / HIGH   | SSRF, prompt injection, resource DoS |
| Pass 1   | Claude   | CRITICAL / HIGH confirmed  | Redirect handling, network binding, proxy-into-perimeter risk |
| Pass 2   | Claude   | MEDIUM / LOW only          | DNS-rebinding window, error-string disclosure |
| Pass 2   | GPT      | CRITICAL / HIGH closed      | Unified untrusted-content wrapper verified |
| Pass 3   | GPT      | No CRITICAL / HIGH         | DNS-rebinding residual; `_peer_ip` fail-open edge |
| Pass 4   | Claude   | No CRITICAL / HIGH         | IPv4-mapped / NAT64 edge; urllib3-contract availability risk |

---

### Key Issues Fixed (OWASP AI Agent Security)

| Threat (OWASP)                   | Status     | Implementation |
|----------------------------------|------------|----------------|
| **SSRF (LLM06 / PIPE06)**        | Addressed  | `safefetch.py` validates schemes and *all* resolved IPs, re-validates every redirect hop, verifies the connected peer IP, fails closed when peer verification is unavailable, and blocks private, link-local, loopback, multicast, reserved, IPv4-mapped, and NAT64 ranges. |
| **Prompt Injection (PIPE01 / LLM01)** | Addressed | `format_untrusted()` prefixes all external tool output with a data-only notice (no closing delimiter to spoof). |
| **Resource Exhaustion (LLM10)**  | Addressed  | Streaming downloads with a hard 25 MiB byte cap (enforced on `Content-Length` and while reading) plus a PDF page cap. |
| **DNS Rebinding**                | Mitigated  | Pre-connect DNS validation + post-connect peer-IP verification. A residual TOCTOU window remains inherent to non-pinned resolution; an integration test tracks the underlying `urllib3`/`requests` behavior. |
| **Error Information Disclosure (LLM02)** | Addressed | Generic error messages returned to the client; resolved internal IPs and raw exceptions logged server-side only. |
| **Supply Chain (LLM03 / ASI04)** | Addressed  | GitHub Actions pinned to commit SHAs (CI + release); volatile runtime dependencies capped to tested major versions. |
| **Network Exposure (PIPE10)**    | Addressed  | Default bind to `127.0.0.1`; explicit opt-in for `0.0.0.0`; `/health` TTL-cached to cap unauthenticated outbound-probe amplification. |

---

### Hardening Changes by Version

**v0.1.6 — core hardening**
- `safefetch.safe_get`: scheme allowlist, resolved-IP validation, manual redirect re-validation, streaming byte cap
- `format_untrusted()` applied to every external-content tool
- `/health` TTL cache; default bind moved to `127.0.0.1`
- GitHub Actions pinned to SHAs; `ddgs` / `youtube-transcript-api` capped to tested major

**v0.1.7 — defense-in-depth**
- Block IPv4-mapped addresses (`::ffff:10.0.0.5`) via explicit unwrap + recheck
- Block NAT64 well-known prefix (`64:ff9b::/96`)
- Post-connect peer-IP check fails closed when the socket cannot be introspected
- `fastmcp>=3.4.2,<4`, `pypdf>=5.0,<6`
- `@pytest.mark.integration` test against a real public URL to catch future `_peer_ip()` / `urllib3` contract breaks

Full regression suite passing across Python 3.11–3.13, including SSRF (rebinding, redirect
chains, round-robin DNS, metadata-endpoint access) and untrusted-content framing tests.

**v0.1.9 — expansion infrastructure**
- Shared fixed-host HTTP transport with one error contract (`SourceError`), hard timeouts, non-JSON handling, bounded cache, and per-source throttling hooks
- Identifier normalization for country/date/year/currency inputs used by the 0.2.0 tools
- `get_current_date` utility so agents can anchor relative requests without guessing
- CLI transport flags (`--host`, `--port`, `--stdio`) and CI/type-check hardening

**v0.2.0 — zero-auth cross-domain expansion**
- Added 13 zero-auth domain tools: weather forecast/history, World Bank indicator search/fetch, FX, crypto, GDELT news, Europe PMC, Bluesky user/profile/feed, SEC company financials, and SEC filing search
- Added live integration coverage across SEC, GDELT, Open-Meteo, Frankfurter, CoinGecko, World Bank, Europe PMC, Bluesky, and cross-domain chains
- Extended OWASP pass to new fixed-host tools: no CRITICAL/HIGH findings remained before release
- Fixed release-wave findings: external upstream error fields are not surfaced unframed, log newlines are scrubbed before server logging, and user-derived URL path segments are encoded

---

### Threats Evaluated and Not Applicable

- **RCE (LLM05 / ASI05):** no `eval`/`exec`/`subprocess`/`os.system` — clean.
- **Tool-loop iteration (ASI02):** stateless single-shot tools; `read_repo` bounded (tree capped, ≤6 files). No agent loop.
- **HITL / rogue agent (ASI09 / ASI10):** no irreversible or privileged actions, no approval flow — N/A.

---

### Current Recommendations (Low Priority)

- Continue monitoring the `urllib3` internals used in `_peer_ip()` (mitigated by the integration test).
- When exposing publicly (`--host 0.0.0.0`), **always** front the server with an authentication + rate-limiting gateway. The server is zero-auth by design.
- For the strongest SSRF posture, consider pinning the validated IP for the actual socket connection (custom resolver/adapter), eliminating the residual DNS-rebinding window entirely.

---

### Responsible Disclosure

If you discover a security vulnerability, please use GitHub private vulnerability
reporting if available, or contact the maintainer directly. Please do not open a public
issue for undisclosed vulnerabilities. Security reports are treated with high priority.

---

**Last updated:** July 2026 · **Version:** v0.2.0

*Security review methodology and tooling: [agent-security-skill](https://github.com/olanokhin/agent-security-skill)*
