"""Web search and URL reading tools."""

from __future__ import annotations

from io import BytesIO
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from pypdf import PdfReader

MAX_TEXT_CHARS = 20_000


def web_search(query: str, max_results: int = 5) -> str:
    """Search the web via DuckDuckGo. No API key required.

    Args:
        query: Search query string.
        max_results: Number of results to return (1–20, default 5).
    """
    max_results = max(1, min(max_results, 20))
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
    return "\n\n".join(
        f"{r.get('title')}\n{r.get('href')}\n{r.get('body')}" for r in results
    ) or "No results found."


def read_url(url: str) -> str:
    """Fetch a web page and return its main text content.

    Args:
        url: Full URL to fetch.
    """
    response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        return f"Could not read page ({exc}). Try a different URL."

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text("\n").splitlines() if line.strip()]
    return "\n".join(lines)[:MAX_TEXT_CHARS]


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
    response = requests.get(pdf_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    if "pdf" not in content_type and not pdf_url.lower().endswith(".pdf"):
        raise ValueError(f"URL did not return a PDF: {pdf_url}")

    reader = PdfReader(BytesIO(response.content))
    chunks = []
    for i, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        if text:
            chunks.append(f"--- Page {i} ---\n{text}")
        if sum(len(c) for c in chunks) >= MAX_TEXT_CHARS:
            break

    text = "\n\n".join(chunks).strip()
    return text[:MAX_TEXT_CHARS] if text else "No text could be extracted from this PDF."
