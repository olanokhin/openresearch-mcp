"""Tests for search_news (GDELT DOC 2.0) — emphasis on rate-limit / non-JSON handling."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from openresearch_mcp.tools.news import _fmt_date, search_news

PATCH = "openresearch_mcp.http.requests.get"


def _ok(data: dict) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = data
    r.raise_for_status.return_value = None
    return r


def _rate_limited() -> MagicMock:
    # GDELT breach: HTTP 429 + a plain-text body.
    r = MagicMock()
    r.status_code = 429
    r.text = "Please limit requests to one every 5 seconds"
    r.raise_for_status.side_effect = requests.HTTPError("429")
    return r


def _non_json() -> MagicMock:
    # 200 but a non-JSON body (GDELT sometimes does this when throttling).
    r = MagicMock()
    r.status_code = 200
    r.text = "Please limit requests to one every 5 seconds"
    r.json.side_effect = ValueError("no json")
    r.raise_for_status.return_value = None
    return r


def _articles(*titles: str) -> dict:
    return {"articles": [
        {
            "title": t, "url": f"https://news.test/{i}", "domain": "news.test",
            "sourcecountry": "United States", "language": "English",
            "seendate": "20260628T120000Z",
        }
        for i, t in enumerate(titles)
    ]}


class TestFmtDate:
    def test_gdelt_timestamp(self):
        assert _fmt_date("20260628T120000Z") == "2026-06-28 12:00"

    def test_garbage_passes_through(self):
        assert _fmt_date("weird") == "weird"

    def test_none(self):
        assert _fmt_date(None) == ""


class TestSearchNews:
    def test_success_renders_articles(self):
        with patch(PATCH, return_value=_ok(_articles("Solar hits record", "Wind grows"))):
            result = search_news("renewable energy")
        assert 'News for "renewable energy" (2 articles)' in result
        assert "Solar hits record" in result
        assert "https://news.test/0" in result
        assert "news.test · United States · English · 2026-06-28 12:00" in result

    def test_wrapped_untrusted(self):
        with patch(PATCH, return_value=_ok(_articles("x"))):
            assert search_news("x").startswith("[untrusted news")

    def test_rate_limited_is_graceful(self):
        # The headline case: 429 must become a retry message, never a crash.
        with patch(PATCH, return_value=_rate_limited()):
            result = search_news("anything")
        assert "GDELT" in result and "rate" in result.lower()

    def test_non_json_body_is_graceful(self):
        with patch(PATCH, return_value=_non_json()):
            result = search_news("anything")
        assert "non-JSON" in result

    def test_no_articles(self):
        with patch(PATCH, return_value=_ok({"articles": []})):
            assert "No recent news" in search_news("zzzqwerty")

    def test_empty_query(self):
        assert "Provide a search topic" in search_news("   ")

    def test_max_results_clamped(self):
        with patch(PATCH, return_value=_ok(_articles("x"))) as g:
            search_news("x", max_results=999)
        assert g.call_args[1]["params"]["maxrecords"] == 50

    def test_non_numeric_max_results_graceful(self):
        with patch(PATCH, side_effect=AssertionError("network must not be hit")):
            assert "Invalid max_results" in search_news("x", max_results="abc")  # type: ignore[arg-type]

    def test_non_dict_article_skipped(self):
        data = {"articles": [{"title": "ok", "url": "u"}, "not-a-dict"]}
        with patch(PATCH, return_value=_ok(data)):
            result = search_news("x")
        assert "ok" in result  # well-formed article still rendered
        assert "(1 articles)" in result  # count reflects rendered, not raw length

    def test_transport_failure_graceful(self):
        with patch(PATCH, side_effect=requests.ConnectionError("boom")):
            assert "Could not reach" in search_news("x")

    def test_repeated_call_served_from_cache(self):
        with patch(PATCH, return_value=_ok(_articles("x"))) as g:
            search_news("same topic")
            search_news("same topic")
        assert g.call_count == 1  # cache_ttl absorbs the re-ask (no second GDELT hit)


@pytest.mark.integration
def test_live_search_news():
    # GDELT is strictly rate-limited; accept either real results or the graceful
    # retry/empty message — the point is it never raises.
    result = search_news("climate change", max_results=3)
    assert isinstance(result, str) and result
    assert result.startswith("[untrusted news") or "GDELT" in result or "No recent news" in result
