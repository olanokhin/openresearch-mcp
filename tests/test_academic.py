"""Smoke tests for search_hacker_news, search_stackoverflow, search_semantic_scholar."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests as req_lib

from openresearch_mcp.tools.academic import (
    search_hacker_news,
    search_semantic_scholar,
    search_stackoverflow,
)


def _ok(data: dict) -> MagicMock:
    r = MagicMock()
    r.json.return_value = data
    r.raise_for_status.return_value = None
    return r


class TestSearchHackerNews:
    def test_returns_story_with_links_and_stats(self):
        with patch("openresearch_mcp.tools.academic.requests.get", return_value=_ok({"hits": [
            {"title": "FastMCP Released", "objectID": "42", "url": "https://example.com", "points": 250, "num_comments": 80}
        ]})):
            result = search_hacker_news("fastmcp")
        assert "FastMCP Released" in result
        assert "https://news.ycombinator.com/item?id=42" in result
        assert "250" in result
        assert "80" in result

    def test_no_results(self):
        with patch("openresearch_mcp.tools.academic.requests.get", return_value=_ok({"hits": []})):
            assert search_hacker_news("xyzzy") == "No results found."

    def test_max_results_clamped_to_20(self):
        with patch("openresearch_mcp.tools.academic.requests.get", return_value=_ok({"hits": []})) as mock_get:
            search_hacker_news("query", max_results=999)
            call = mock_get.call_args
            assert call[1]["params"]["hitsPerPage"] == 20


class TestSearchStackOverflow:
    def test_returns_question_with_body(self):
        with patch("openresearch_mcp.tools.academic.requests.get", return_value=_ok({"items": [
            {"title": "How to use FastMCP?", "link": "https://stackoverflow.com/q/1", "score": 12, "answer_count": 3, "body": "<p>I want to use <code>FastMCP</code>.</p>"}
        ]})):
            result = search_stackoverflow("fastmcp usage")
        assert "How to use FastMCP?" in result
        assert "stackoverflow.com/q/1" in result
        assert "FastMCP" in result
        assert "12" in result

    def test_no_results(self):
        with patch("openresearch_mcp.tools.academic.requests.get", return_value=_ok({"items": []})):
            assert search_stackoverflow("xyzzy") == "No results found."

    def test_max_results_clamped_to_10(self):
        with patch("openresearch_mcp.tools.academic.requests.get", return_value=_ok({"items": []})) as mock_get:
            search_stackoverflow("query", max_results=999)
            call = mock_get.call_args
            assert call[1]["params"]["pagesize"] == 10


class TestSearchSemanticScholar:
    def test_returns_paper_with_authors_and_abstract(self):
        with patch("openresearch_mcp.tools.academic.requests.get", return_value=_ok({"data": [{
            "title": "Attention Is All You Need",
            "year": 2017,
            "url": "https://semanticscholar.org/paper/1",
            "openAccessPdf": {"url": "https://arxiv.org/pdf/1706.03762"},
            "authors": [{"name": "Vaswani"}, {"name": "Shazeer"}, {"name": "Parmar"}, {"name": "Fourth Author"}],
            "abstract": "The dominant sequence model is based on RNNs.",
        }]})):
            result = search_semantic_scholar("transformer attention")
        assert "Attention Is All You Need" in result
        assert "2017" in result
        assert "Vaswani" in result
        assert "https://arxiv.org/pdf/1706.03762" in result
        assert "dominant sequence model" in result
        assert "Fourth Author" not in result  # only first 3 authors shown

    def test_no_open_access_pdf_omits_pdf_line(self):
        with patch("openresearch_mcp.tools.academic.requests.get", return_value=_ok({"data": [{
            "title": "Paywalled Paper",
            "year": 2020,
            "url": "https://semanticscholar.org/paper/2",
            "openAccessPdf": None,
            "authors": [],
            "abstract": "No public PDF.",
        }]})):
            result = search_semantic_scholar("paywalled topic")
        assert "Paywalled Paper" in result
        assert "PDF:" not in result

    def test_no_results(self):
        with patch("openresearch_mcp.tools.academic.requests.get", return_value=_ok({"data": []})):
            assert search_semantic_scholar("xyzzy") == "No results found."

    def test_429_falls_back_to_duckduckgo(self):
        mock_429 = MagicMock()
        mock_429.status_code = 429
        err = req_lib.HTTPError(response=mock_429)
        bad_resp = MagicMock()
        bad_resp.raise_for_status.side_effect = err

        ddg_hits = [{"title": "Scholar via DDG", "href": "https://semanticscholar.org/1", "body": "DDG snippet"}]
        with patch("openresearch_mcp.tools.academic.requests.get", return_value=bad_resp), \
             patch("openresearch_mcp.tools.academic.DDGS") as mock_ddgs:
            mock_ddgs.return_value.__enter__.return_value.text.return_value = ddg_hits
            result = search_semantic_scholar("neural networks")
        assert "Scholar via DDG" in result
        assert "DDG snippet" in result

    def test_429_empty_ddg_fallback_returns_message(self):
        mock_429 = MagicMock()
        mock_429.status_code = 429
        bad_resp = MagicMock()
        bad_resp.raise_for_status.side_effect = req_lib.HTTPError(response=mock_429)

        with patch("openresearch_mcp.tools.academic.requests.get", return_value=bad_resp), \
             patch("openresearch_mcp.tools.academic.DDGS") as mock_ddgs:
            mock_ddgs.return_value.__enter__.return_value.text.return_value = []
            result = search_semantic_scholar("neural networks")
        assert "rate limited" in result.lower()
