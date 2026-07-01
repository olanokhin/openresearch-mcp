"""US company fundamentals via SEC EDGAR XBRL — zero-auth (contact UA only).

SEC asks every client to identify itself with a contact in the User-Agent (any
email; no registration/key). Set ``SEC_USER_AGENT`` to your own contact to be a
good citizen; a default is used otherwise. Data is annual figures pulled from
10-K filings; US filers only (ticker → CIK via SEC's own ticker map).
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote as urlquote

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
        return f"No annual XBRL financial data found for {ticker.strip().upper()}."

    header = f"{name} ({ticker.strip().upper()}) — annual fundamentals from SEC 10-K filings (USD):"
    body = header + "\n\n" + "\n\n".join(sections)
    return format_untrusted("SEC EDGAR", body[:MAX_TEXT_CHARS])


_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"


def _filing_url(hit: dict) -> str | None:
    """Build a direct document URL from an efts hit (``_id`` = 'accession:filename')."""
    doc_id = str(hit.get("_id") or "")
    src = hit.get("_source") if isinstance(hit.get("_source"), dict) else {}
    ciks = src.get("ciks") if isinstance(src, dict) else None
    if ":" not in doc_id or not isinstance(ciks, list) or not ciks:
        return None
    accession, filename = doc_id.split(":", 1)
    cik = str(ciks[0]).lstrip("0")
    if not cik or not filename:
        return None
    accession_dir = urlquote(accession.replace("-", ""), safe="")
    filename_safe = urlquote(filename, safe="")
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_dir}/{filename_safe}"


@tool_safe
def search_sec_filings(query: str, forms: str = "", max_results: int = 10) -> str:
    """Full-text search of SEC EDGAR filings by keyword/company. No API key.

    Finds 10-K / 10-Q / 8-K (and other) filings mentioning a term, with a direct
    document URL to feed into read_url or read_pdf.

    Args:
        query: Search terms, e.g. "supply chain risk" or a company name.
        forms: Optional comma-separated form filter, e.g. "10-K" or "10-K,10-Q".
        max_results: Number of filings to return (1–25, default 10).
    """
    if not query or not query.strip():
        return "Provide search terms, e.g. 'climate risk' or a company name."
    try:
        n = max(1, min(int(max_results), 25))
    except (TypeError, ValueError):
        return f"Invalid max_results {max_results!r}; provide a whole number (1–25)."

    params: dict[str, Any] = {"q": query.strip()}
    if forms and forms.strip():
        params["forms"] = forms.strip()
    data = fetch_json(
        _EFTS_URL, source="SEC", headers={"User-Agent": _sec_ua()}, params=params, timeout=20
    )

    hits_root = data.get("hits") if isinstance(data, dict) else None
    hits = hits_root.get("hits") if isinstance(hits_root, dict) else None
    hits = [h for h in hits if isinstance(h, dict)] if isinstance(hits, list) else []
    if not hits:
        return f"No SEC filings found for {query!r}."

    total = (hits_root.get("total") or {}).get("value") if isinstance(hits_root, dict) else None
    lines = [f'Found {total} SEC filings for "{query.strip()}" (showing up to {n}):']
    for hit in hits[:n]:
        src = hit.get("_source") if isinstance(hit.get("_source"), dict) else {}
        names = src.get("display_names") if isinstance(src, dict) else None
        who = names[0] if isinstance(names, list) and names else "Unknown filer"
        meta = " · ".join(str(x) for x in (src.get("form"), src.get("file_date")) if x)
        entry = [f"\n{who}"]
        if meta:
            entry.append(meta)
        url = _filing_url(hit)
        if url:
            entry.append(f"Document (feed to read_url/read_pdf): {url}")
        lines.append("\n".join(entry))

    return format_untrusted("SEC EDGAR", "\n".join(lines)[:MAX_TEXT_CHARS])
