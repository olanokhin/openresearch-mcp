# Security Policy and Hardening Report

**openresearch-mcp** is a zero-auth MCP server. Therefore, strong security controls around external data fetching and tool outputs are a top priority.

## Security Hardening Journey

The project was reviewed and hardened using **[agent-security-skill](https://github.com/olanokhin/agent-security-skill)**,
an OWASP-aligned AI agent security review skill developed by the maintainer.

This was not a generic checklist pass: findings from the skill were applied directly to
openresearch-mcp and resulted in concrete code, dependency, workflow, and test changes.

### Summary
- **Before review:** The server had several high-impact AI-agent security gaps, including SSRF exposure, raw external content returned to agents, and unbounded fetch/parsing paths.
- **After v0.1.8:** No known CRITICAL or HIGH findings remain from the reviewed scope. Remaining items are defense-in-depth or operational controls.

**Current version:** v0.1.8 (security documentation release)

---

### Review Timeline

| Iteration       | Model    | Status                          | Key Findings |
|-----------------|----------|----------------------------------|--------------|
| Run 1           | GPT     | Multiple CRITICAL/HIGH          | SSRF, prompt injection, resource DoS |
| Run 1           | Claude  | CRITICAL/HIGH confirmed         | Redirects, binding, network proxy risks |
| Run 2           | Claude  | MEDIUM/LOW only                 | DNS Rebinding, error disclosure |
| Run 2           | GPT     | CRITICAL/HIGH closed            | Unified untrusted content wrapper |
| Run 3           | GPT     | No CRITICAL/HIGH                | DNS Rebinding residual |
| Final Run       | Claude  | No CRITICAL/HIGH                | Minor edge cases only |

---

### Key Issues Fixed (OWASP AI Agent Security)

| Threat (OWASP)                        | Status              | Implementation |
|---------------------------------------|---------------------|--------------|
| **SSRF (LLM06 / PIPE06)**             | Addressed           | `safefetch.py` validates schemes and resolved IPs, re-validates redirects, checks the connected peer IP, fails closed when peer verification is unavailable, and blocks private, link-local, loopback, IPv4-mapped, and NAT64 ranges. |
| **Prompt Injection (PIPE01)**         | Addressed           | `format_untrusted()` labels external tool output as untrusted data across external-content tools. |
| **Resource Exhaustion (LLM10)**       | Addressed           | Streaming downloads, hard 25 MiB byte limit, and PDF page cap. |
| **DNS Rebinding**                     | Mitigated           | Pre-connect DNS validation plus post-connect peer-IP verification; integration test tracks urllib3/requests behavior. |
| **Error Information Disclosure**      | Addressed           | Generic error messages to clients; details logged server-side only. |
| **Supply Chain (LLM03 / ASI04)**      | Addressed           | GitHub Actions pinned to commit SHAs; volatile runtime dependencies capped to tested major versions. |
| **Network Exposure**                  | Addressed           | Default bind to `127.0.0.1`, with documentation for gateway use when exposed beyond loopback. |

---

### Final Hardening Changes (v0.1.7)

- `fastmcp>=3.4.2,<4` (keeps latest 3.x while preventing breaking changes)
- `pypdf>=5.0,<6`
- Explicit blocking of:
  - IPv4-mapped private addresses (`::ffff:10.0.0.5` etc.)
  - NAT64 well-known prefix (`64:ff9b::/96`)
- Added `@pytest.mark.integration` test with real public URL to detect future `_peer_ip()` / `urllib3` contract breaks
- All tests passing: **81 passed**
- Default binding remains `127.0.0.1` for security

---

### Current Recommendations (Low Priority)

- Continue monitoring `urllib3` internals used in `_peer_ip()` (mitigated by integration test).
- When exposing publicly (`--host 0.0.0.0`), **always** put an authentication + rate-limiting gateway in front.

---

### Responsible Disclosure

If you discover a security vulnerability, use GitHub private vulnerability reporting if available, or contact the maintainer directly.

We treat security reports with high priority.

---

**Last updated:** June 2026  
**Version:** v0.1.8

*Security improvements powered by [agent-security-skill](https://github.com/olanokhin/agent-security-skill)*
