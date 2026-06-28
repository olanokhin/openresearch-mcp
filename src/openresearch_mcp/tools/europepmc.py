"""Biomedical literature search via Europe PMC — zero-auth, no API key.

Europe PMC covers biomedicine + life sciences with open-access full text where
available. The key signal is ``isOpenAccess``: for OA papers we surface a PDF URL
the agent can hand straight to ``read_pdf`` (the chaining gate); for paywalled ones
we say so and withhold a PDF link, so read_pdf isn't pointed at a subscription wall.
"""

from __future__ import annotations

from openresearch_mcp.constants import MAX_TEXT_CHARS
from openresearch_mcp.formatting import format_untrusted
from openresearch_mcp.http import fetch_json, tool_safe

_EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
_OA_AVAILABILITY = {"open access", "free"}


def _oa_pdf_url(result: dict) -> str | None:
    """Return an open/free PDF URL from a result's fullTextUrlList, if any.

    Defensive: the nested shape is external data — every level may be missing or
    the wrong type, and that must skip, not crash (@tool_safe catches only transport).
    """
    full_text = result.get("fullTextUrlList")
    if not isinstance(full_text, dict):
        return None
    url_list = full_text.get("fullTextUrl")
    if not isinstance(url_list, list):
        return None
    for entry in url_list:
        if not isinstance(entry, dict):
            continue
        style = str(entry.get("documentStyle", "")).lower()
        availability = str(entry.get("availability", "")).strip().lower()
        if style == "pdf" and availability in _OA_AVAILABILITY:
            url = entry.get("url")
            if url:
                return str(url)
    return None


@tool_safe
def search_europepmc(query: str, max_results: int = 5) -> str:
    """Search biomedical/life-science literature (Europe PMC). No API key required.

    Flags open-access papers and, for them, gives a PDF URL to pass to read_pdf.
    Paywalled papers are returned too but without a PDF link.

    Args:
        query: Search query, e.g. "CRISPR base editing" or "GLP-1 obesity".
        max_results: Number of papers to return (1–25, default 5).
    """
    if not query or not query.strip():
        return "Provide a search query, e.g. 'CRISPR gene editing'."
    try:
        n = max(1, min(int(max_results), 25))
    except (TypeError, ValueError):
        return f"Invalid max_results {max_results!r}; provide a whole number (1–25)."

    data = fetch_json(
        _EUROPEPMC,
        source="Europe PMC",
        params={"query": query.strip(), "format": "json", "pageSize": n, "resultType": "core"},
        timeout=20,
    )

    results = ((data.get("resultList") or {}).get("result")) if isinstance(data, dict) else None
    if not isinstance(results, list) or not results:
        return f"No papers found for {query!r}."
    papers = [r for r in results if isinstance(r, dict)]
    if not papers:
        return f"No papers found for {query!r}."

    hit_count = data.get("hitCount") if isinstance(data, dict) else None
    header = f'Found {hit_count} papers for "{query.strip()}" (showing {len(papers)}):'
    lines = [header]
    for r in papers:
        authors = str(r.get("authorString") or "")
        if len(authors) > 120:
            authors = authors[:120].rstrip(", ") + " et al."
        journal = " · ".join(
            str(x) for x in (r.get("journalTitle"), r.get("pubYear")) if x
        )
        entry = [f"\n{r.get('title') or 'Untitled'}"]
        if authors:
            entry.append(authors)
        if journal:
            entry.append(journal)
        if r.get("doi"):
            entry.append(f"DOI: {r['doi']}")
        if r.get("isOpenAccess") == "Y":
            pdf = _oa_pdf_url(r)
            entry.append(f"Open access — PDF (feed to read_pdf): {pdf}" if pdf else "Open access")
        else:
            entry.append("Subscription required — no open PDF")
        lines.append("\n".join(entry))

    return format_untrusted("Europe PMC", "\n".join(lines)[:MAX_TEXT_CHARS])
