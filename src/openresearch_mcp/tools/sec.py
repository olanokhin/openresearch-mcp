"""US company fundamentals via SEC EDGAR XBRL — zero-auth (contact UA only).

SEC asks every client to identify itself with a contact in the User-Agent (any
email; no registration/key). Set ``SEC_USER_AGENT`` to your own contact to be a
good citizen; a default is used otherwise. Data is annual figures pulled from
10-K filings; US filers only (ticker → CIK via SEC's own ticker map).
"""

from __future__ import annotations

import os

from openresearch_mcp.constants import MAX_TEXT_CHARS
from openresearch_mcp.formatting import format_untrusted
from openresearch_mcp.http import SourceError, fetch_json, tool_safe

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json"
_YEARS = 5  # most recent fiscal years to show per metric

# (label, [candidate us-gaap tags, tried in order — revenue tag varies by filer/era]).
_METRICS: list[tuple[str, list[str]]] = [
    ("Revenue", ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"]),
    ("Net income", ["NetIncomeLoss"]),
    ("Total assets", ["Assets"]),
    ("Shareholders' equity", ["StockholdersEquity"]),
]


def _sec_ua() -> str:
    # SEC's fair-access policy wants a contact email in the UA; it 403s a URL-only
    # string AND some domains (e.g. noreply.github.com). Default to the IANA-reserved
    # example.com placeholder, which SEC accepts, so the tool works zero-auth out of
    # the box; heavy/shared deployments should set SEC_USER_AGENT to a real contact.
    return os.getenv("SEC_USER_AGENT") or "openresearch-mcp (contact: openresearch-mcp@example.com)"


def _resolve(ticker: str) -> tuple[int, str] | None:
    """Map a ticker to (CIK, company name) via SEC's ticker file. Cached (near-static)."""
    data = fetch_json(
        _TICKERS_URL,
        source="SEC",
        headers={"User-Agent": _sec_ua()},
        timeout=20,
        cache_ttl=86400,
    )
    if not isinstance(data, dict):
        return None
    want = ticker.strip().upper()
    for row in data.values():
        if isinstance(row, dict) and str(row.get("ticker", "")).upper() == want:
            try:
                return int(row["cik_str"]), str(row.get("title") or want)
            except (KeyError, TypeError, ValueError):
                return None
    return None


def _annual(cik: int, tag: str) -> dict[str, int]:
    """Return {fiscal_year: value} from 10-K filings for one concept, or {} if absent.

    Catches 404 SourceError locally: a missing concept must skip the metric, not
    abort the whole tool. Other SEC errors (403/rate-limit/network) are re-raised
    so @tool_safe can surface the real source failure instead of a misleading
    "no data" result. Dedupes by fiscal-year-end (filings restate prior years).
    """
    try:
        data = fetch_json(
            _CONCEPT_URL.format(cik=cik, tag=tag),
            source="SEC",
            headers={"User-Agent": _sec_ua()},
            timeout=20,
        )
    except SourceError as exc:
        if exc.status_code == 404:
            return {}
        raise
    units = (data.get("units") or {}).get("USD") if isinstance(data, dict) else None
    if not isinstance(units, list):
        return {}
    by_year: dict[str, int] = {}
    for u in units:
        if not isinstance(u, dict) or u.get("form") != "10-K":
            continue
        end, val = u.get("end"), u.get("val")
        if not end or not isinstance(val, int | float):
            continue
        by_year[str(end)[:4]] = int(val)  # one value per fiscal year; later filing wins
    return by_year


@tool_safe
def get_company_financials(ticker: str) -> str:
    """Annual fundamentals (revenue, earnings, assets) for a US-listed company. No key.

    Pulls figures from SEC EDGAR 10-K filings. US filers only. Set SEC_USER_AGENT to
    your contact email to comply with SEC's fair-access policy (a default is used otherwise).

    Args:
        ticker: Stock ticker symbol, e.g. "AAPL", "MSFT".
    """
    if not ticker or not ticker.strip():
        return "Provide a stock ticker, e.g. 'AAPL'."

    resolved = _resolve(ticker)
    if resolved is None:
        return f"No SEC filer found for ticker {ticker.strip().upper()!r} (US-listed companies only)."
    cik, name = resolved

    sections: list[str] = []
    for label, tags in _METRICS:
        series: dict[str, int] = {}
        for tag in tags:
            series = _annual(cik, tag)
            if series:
                break
        if not series:
            continue
        recent = sorted(series, reverse=True)[:_YEARS]
        lines = [f"{label}:"] + [f"  {year}: {series[year]:,}" for year in recent]
        sections.append("\n".join(lines))

    if not sections:
        return f"No annual XBRL financial data found for {name} ({ticker.strip().upper()})."

    header = f"{name} ({ticker.strip().upper()}) — annual fundamentals from SEC 10-K filings (USD):"
    body = header + "\n\n" + "\n\n".join(sections)
    return format_untrusted("SEC EDGAR", body[:MAX_TEXT_CHARS])
