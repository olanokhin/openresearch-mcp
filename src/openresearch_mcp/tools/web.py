"""Web search and URL reading tools."""

from __future__ import annotations

import logging
from io import BytesIO
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from pypdf import PdfReader

from openresearch_mcp.formatting import format_untrusted
from openresearch_mcp.safefetch import UnsafeURLError, safe_get

logger = logging.getLogger(__name__)

MAX_TEXT_CHARS = 20_000
MAX_PDF_PAGES = 50


def web_search(query: str, max_results: int = 5, site: str | None = None) -> str:
    """Search the web via DuckDuckGo. No API key required.

    Args:
        query: Search query string.
        max_results: Number of results to return (1–20, default 5).
        site: Restrict results to a specific domain, e.g. "arxiv.org" or "github.com".
    """
    if site:
        query = f"site:{site} {query}"
    max_results = max(1, min(max_results, 20))
    results = list(DDGS().text(query, max_results=max_results))
    body = "\n\n".join(
        f"{r.get('title')}\n{r.get('href')}\n{r.get('body')}" for r in results
    )
    return format_untrusted("web search", body) if body else "No results found."


def read_url(url: str) -> str:
    """Fetch a web page and return its main text content.

    Args:
        url: Full URL to fetch.
    """
    try:
        response = safe_get(
            url, timeout=20, headers={"User-Agent": "Mozilla/5.0"}, max_bytes=10 * 1024 * 1024
        )
        response.raise_for_status()
    except UnsafeURLError as exc:
        logger.warning("read_url refused %s: %s", url, exc)
        return "Refused to fetch URL: address not permitted."
    except requests.HTTPError as exc:
        # HTTP status (404/403/…) is about the target the caller already knows — safe to surface.
        return f"Could not read page ({exc}). Try a different URL."
    except requests.RequestException as exc:
        logger.warning("read_url network error %s: %s", url, exc)
        return "Network error fetching page."

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text("\n").splitlines() if line.strip()]
    return format_untrusted("web page", "\n".join(lines)[:MAX_TEXT_CHARS])


def _normalize_pdf_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("arxiv.org"):
        for prefix in ("/abs/", "/html/", "/pdf/"):
            if parsed.path.startswith(prefix):
                paper_id = parsed.path.removeprefix(prefix)
                return f"https://arxiv.org/pdf/{paper_id}"
    return url


def read_pdf(url: str) -> str:
    """Download and extract text from a PDF. Handles arXiv abstract/HTML/PDF URLs.

    Args:
        url: URL to a PDF file or arXiv paper page.
    """
    pdf_url = _normalize_pdf_url(url)
    try:
        response = safe_get(pdf_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
    except UnsafeURLError as exc:
        logger.warning("read_pdf refused %s: %s", pdf_url, exc)
        return "Refused to fetch PDF: address not permitted."
    except requests.HTTPError as exc:
        return f"Could not fetch PDF ({exc}). Check the URL and try again."
    except requests.RequestException as exc:
        logger.warning("read_pdf network error %s: %s", pdf_url, exc)
        return "Network error fetching PDF."

    content_type = response.headers.get("content-type", "").lower()
    if "pdf" not in content_type and not pdf_url.lower().endswith(".pdf"):
        return f"URL did not return a PDF (content-type: {content_type}): {pdf_url}"

    try:
        reader = PdfReader(BytesIO(response.content))
    except Exception as exc:
        return f"Could not parse PDF: {exc}"
    chunks = []
    for i, page in enumerate(reader.pages[:MAX_PDF_PAGES], 1):
        text = (page.extract_text() or "").strip()
        if text:
            chunks.append(f"--- Page {i} ---\n{text}")
        if sum(len(c) for c in chunks) >= MAX_TEXT_CHARS:
            break

    text = "\n\n".join(chunks).strip()
    if not text:
        return "No text could be extracted from this PDF."
    return format_untrusted("PDF", text[:MAX_TEXT_CHARS])
