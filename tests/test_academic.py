"""Smoke tests for search_hacker_news, search_stackoverflow, search_openalex."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from openresearch_mcp.tools.academic import (
    _reconstruct_abstract,
    search_hacker_news,
    search_openalex,
    search_stackoverflow,
)


def _ok(data: dict) -> MagicMock:
    r = MagicMock()
    r.json.return_value = data
    r.raise_for_status.return_value = None
    return r


class TestSearchHackerNews:
    def test_returns_story_with_links_and_stats(self):
        with patch("openresearch_mcp.http.requests.get", return_value=_ok({"hits": [
            {"title": "FastMCP Released", "objectID": "42", "url": "https://example.com", "points": 250, "num_comments": 80}
        ]})):
            result = search_hacker_news("fastmcp")
        assert "FastMCP Released" in result
        assert "https://news.ycombinator.com/item?id=42" in result
        assert "250" in result
        assert "80" in result

    def test_no_results(self):
        with patch("openresearch_mcp.http.requests.get", return_value=_ok({"hits": []})):
            assert search_hacker_news("xyzzy") == "No results found."

    def test_max_results_clamped_to_20(self):
        with patch("openresearch_mcp.http.requests.get", return_value=_ok({"hits": []})) as mock_get:
            search_hacker_news("query", max_results=999)
            call = mock_get.call_args
            assert call[1]["params"]["hitsPerPage"] == 20


class TestSearchStackOverflow:
    def test_returns_question_with_body(self):
        with patch("openresearch_mcp.http.requests.get", return_value=_ok({"items": [
            {"title": "How to use FastMCP?", "link": "https://stackoverflow.com/q/1", "score": 12, "answer_count": 3, "body": "<p>I want to use <code>FastMCP</code>.</p>"}
        ]})):
            result = search_stackoverflow("fastmcp usage")
        assert "How to use FastMCP?" in result
        assert "stackoverflow.com/q/1" in result
        assert "FastMCP" in result
        assert "12" in result

    def test_no_results(self):
        with patch("openresearch_mcp.http.requests.get", return_value=_ok({"items": []})):
            assert search_stackoverflow("xyzzy") == "No results found."

    def test_max_results_clamped_to_10(self):
        with patch("openresearch_mcp.http.requests.get", return_value=_ok({"items": []})) as mock_get:
            search_stackoverflow("query", max_results=999)
            call = mock_get.call_args
            assert call[1]["params"]["pagesize"] == 10


class TestReconstructAbstract:
    def test_basic_reconstruction(self):
        inv_idx = {"Hello": [0], "world": [1]}
        assert _reconstruct_abstract(inv_idx) == "Hello world"

    def test_out_of_order_keys(self):
        inv_idx = {"second": [1], "first": [0], "third": [2]}
        assert _reconstruct_abstract(inv_idx) == "first second third"

    def test_word_at_multiple_positions(self):
        inv_idx = {"the": [0, 2], "cat": [1], "sat": [3]}
        assert _reconstruct_abstract(inv_idx) == "the cat the sat"

    def test_none_returns_empty(self):
        assert _reconstruct_abstract(None) == ""

    def test_empty_dict_returns_empty(self):
        assert _reconstruct_abstract({}) == ""


def _openalex_work(**overrides) -> dict:
    base = {
        "title": "Attention Is All You Need",
        "publication_year": 2017,
        "doi": "https://doi.org/10.48550/arxiv.1706.03762",
        "primary_location": {"landing_page_url": "https://doi.org/10.48550/arxiv.1706.03762"},
        "open_access": {"oa_url": "https://arxiv.org/pdf/1706.03762"},
        "authorships": [
            {"author": {"display_name": "Vaswani"}},
            {"author": {"display_name": "Shazeer"}},
            {"author": {"display_name": "Parmar"}},
            {"author": {"display_name": "Fourth Author"}},
        ],
        "abstract_inverted_index": {"The": [0], "dominant": [1], "model": [2]},
    }
    return {**base, **overrides}


class TestSearchOpenAlex:
    def test_returns_paper_with_authors_and_abstract(self):
        with patch("openresearch_mcp.http.requests.get", return_value=_ok(
            {"results": [_openalex_work()]}
        )):
            result = search_openalex("transformer attention")
        assert "Attention Is All You Need" in result
        assert "2017" in result
        assert "Vaswani" in result
        assert "Shazeer" in result
        assert "https://arxiv.org/pdf/1706.03762" in result
        assert "dominant" in result
        assert "Fourth Author" not in result  # only first 3 authors shown

    def test_no_open_access_pdf_omits_pdf_line(self):
        work = _openalex_work(open_access={"oa_url": None})
        with patch("openresearch_mcp.http.requests.get", return_value=_ok({"results": [work]})):
            result = search_openalex("paywalled topic")
        assert "Attention Is All You Need" in result
        assert "PDF:" not in result

    def test_no_abstract_omits_abstract_line(self):
        work = _openalex_work(abstract_inverted_index=None)
        with patch("openresearch_mcp.http.requests.get", return_value=_ok({"results": [work]})):
            result = search_openalex("no abstract paper")
        assert "Abstract:" not in result

    def test_no_results(self):
        with patch("openresearch_mcp.http.requests.get", return_value=_ok({"results": []})):
            assert search_openalex("xyzzy") == "No results found."

    def test_max_results_clamped_to_10(self):
        with patch("openresearch_mcp.http.requests.get", return_value=_ok({"results": []})) as mock_get:
            search_openalex("query", max_results=999)
            call = mock_get.call_args
            assert call[1]["params"]["per_page"] == 10

    def test_openalex_email_in_user_agent(self):
        import os
        with patch("openresearch_mcp.http.requests.get", return_value=_ok({"results": []})) as mock_get, \
             patch.dict(os.environ, {"OPENALEX_EMAIL": "test@example.com"}):
            search_openalex("query")
            headers = mock_get.call_args[1]["headers"]
            assert "test@example.com" in headers["User-Agent"]
