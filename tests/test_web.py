"""Smoke tests for web_search, read_url, and read_pdf."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests as req_lib

from openresearch_mcp.tools.web import _normalize_pdf_url, read_pdf, read_url, web_search


class TestWebSearch:
    def test_returns_formatted_results(self):
        hits = [{"title": "MCP Guide", "href": "https://example.com", "body": "Snippet text"}]
        with patch("openresearch_mcp.tools.web.DDGS") as mock_ddgs:
            mock_ddgs.return_value.__enter__.return_value.text.return_value = hits
            result = web_search("mcp python")
        assert "MCP Guide" in result
        assert "https://example.com" in result
        assert "Snippet text" in result

    def test_no_results(self):
        with patch("openresearch_mcp.tools.web.DDGS") as mock_ddgs:
            mock_ddgs.return_value.__enter__.return_value.text.return_value = []
            assert web_search("xyzzy nonsense") == "No results found."

    def test_max_results_clamped_to_20(self):
        with patch("openresearch_mcp.tools.web.DDGS") as mock_ddgs:
            mock_ddgs.return_value.__enter__.return_value.text.return_value = []
            web_search("query", max_results=999)
            call = mock_ddgs.return_value.__enter__.return_value.text.call_args
            assert call[1]["max_results"] == 20

    def test_site_parameter_prepends_operator(self):
        with patch("openresearch_mcp.tools.web.DDGS") as mock_ddgs:
            mock_ddgs.return_value.__enter__.return_value.text.return_value = []
            web_search("transformer attention", site="arxiv.org")
            call = mock_ddgs.return_value.__enter__.return_value.text.call_args
            assert call[0][0] == "site:arxiv.org transformer attention"

    def test_no_site_leaves_query_unchanged(self):
        with patch("openresearch_mcp.tools.web.DDGS") as mock_ddgs:
            mock_ddgs.return_value.__enter__.return_value.text.return_value = []
            web_search("transformer attention")
            call = mock_ddgs.return_value.__enter__.return_value.text.call_args
            assert call[0][0] == "transformer attention"


class TestReadUrl:
    def _resp(self, html: str) -> MagicMock:
        r = MagicMock()
        r.text = html
        r.raise_for_status.return_value = None
        return r

    def test_extracts_body_text(self):
        with patch("openresearch_mcp.tools.web.requests.get", return_value=self._resp(
            "<html><body><p>Hello world</p></body></html>"
        )):
            assert "Hello world" in read_url("https://example.com")

    def test_strips_scripts_and_styles(self):
        with patch("openresearch_mcp.tools.web.requests.get", return_value=self._resp(
            "<html><body><p>Keep this</p><script>drop</script><style>drop</style></body></html>"
        )):
            result = read_url("https://example.com")
        assert "Keep this" in result
        assert "drop" not in result

    def test_http_error_returns_message(self):
        r = MagicMock()
        r.raise_for_status.side_effect = req_lib.HTTPError("404 Not Found")
        with patch("openresearch_mcp.tools.web.requests.get", return_value=r):
            result = read_url("https://example.com/gone")
        assert "Could not read page" in result


class TestNormalizePdfUrl:
    def test_arxiv_abs_becomes_pdf(self):
        assert _normalize_pdf_url("https://arxiv.org/abs/2301.00001") == "https://arxiv.org/pdf/2301.00001"

    def test_arxiv_html_becomes_pdf(self):
        assert _normalize_pdf_url("https://arxiv.org/html/2301.00001") == "https://arxiv.org/pdf/2301.00001"

    def test_arxiv_pdf_passthrough(self):
        url = "https://arxiv.org/pdf/2301.00001"
        assert _normalize_pdf_url(url) == url

    def test_non_arxiv_passthrough(self):
        url = "https://example.com/paper.pdf"
        assert _normalize_pdf_url(url) == url


class TestReadPdf:
    def _pdf_resp(self) -> MagicMock:
        r = MagicMock()
        r.content = b"%PDF-1.4 fake"
        r.headers = {"content-type": "application/pdf"}
        r.raise_for_status.return_value = None
        return r

    def _reader(self, *page_texts: str) -> MagicMock:
        pages = []
        for text in page_texts:
            p = MagicMock()
            p.extract_text.return_value = text
            pages.append(p)
        reader = MagicMock()
        reader.pages = pages
        return reader

    def test_extracts_text_from_pages(self):
        with patch("openresearch_mcp.tools.web.requests.get", return_value=self._pdf_resp()), \
             patch("openresearch_mcp.tools.web.PdfReader", return_value=self._reader("Page one content")):
            result = read_pdf("https://arxiv.org/abs/2301.00001")
        assert "Page one content" in result
        assert "Page 1" in result

    def test_multiple_pages_joined(self):
        with patch("openresearch_mcp.tools.web.requests.get", return_value=self._pdf_resp()), \
             patch("openresearch_mcp.tools.web.PdfReader", return_value=self._reader("First", "Second")):
            result = read_pdf("https://example.com/paper.pdf")
        assert "First" in result
        assert "Second" in result

    def test_empty_pages_returns_fallback(self):
        with patch("openresearch_mcp.tools.web.requests.get", return_value=self._pdf_resp()), \
             patch("openresearch_mcp.tools.web.PdfReader", return_value=self._reader("")):
            result = read_pdf("https://example.com/paper.pdf")
        assert "No text could be extracted" in result
