"""Tests for search_europepmc — emphasis on the open-access → read_pdf gate."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from openresearch_mcp.tools.europepmc import _oa_pdf_url, search_europepmc

PATCH = "openresearch_mcp.http.requests.get"

_PDF = "https://europepmc.org/articles/PMC1?pdf=render"


def _ok(data: dict) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = data
    r.raise_for_status.return_value = None
    return r


def _ft(*entries: tuple[str, str, str]) -> dict:
    return {"fullTextUrlList": {"fullTextUrl": [
        {"documentStyle": ds, "availability": av, "url": url} for ds, av, url in entries
    ]}}


def _result(**over) -> dict:
    base = {
        "title": "A paper", "authorString": "Smith J, Doe A", "journalTitle": "Nature",
        "pubYear": "2026", "doi": "10.1/x", "isOpenAccess": "N",
        "fullTextUrlList": {"fullTextUrl": []},
    }
    return {**base, **over}


def _search(results: list, hit=100) -> dict:
    return {"hitCount": hit, "resultList": {"result": results}}


class TestOaPdfUrl:
    def test_picks_open_access_pdf(self):
        r = _ft(("html", "Open access", "h"), ("pdf", "Open access", _PDF))
        assert _oa_pdf_url(r) == _PDF

    def test_accepts_free_availability(self):
        r = _ft(("pdf", "Free", _PDF))
        assert _oa_pdf_url(r) == _PDF

    def test_accepts_case_variants(self):
        r = _ft(("PDF", " Open Access ", _PDF))
        assert _oa_pdf_url(r) == _PDF

    def test_skips_subscription_pdf(self):
        r = _ft(("pdf", "Subscription required", "x"))
        assert _oa_pdf_url(r) is None

    def test_skips_non_pdf(self):
        r = _ft(("html", "Open access", "x"))
        assert _oa_pdf_url(r) is None

    def test_malformed_shapes_return_none(self):
        assert _oa_pdf_url({}) is None
        assert _oa_pdf_url({"fullTextUrlList": "nope"}) is None
        assert _oa_pdf_url({"fullTextUrlList": {"fullTextUrl": "nope"}}) is None
        assert _oa_pdf_url({"fullTextUrlList": {"fullTextUrl": ["bad", 1]}}) is None


class TestSearchEuropePMC:
    def test_open_access_surfaces_pdf_for_read_pdf(self):
        r = _result(isOpenAccess="Y", **_ft(("pdf", "Open access", _PDF)))
        with patch(PATCH, return_value=_ok(_search([r]))):
            result = search_europepmc("crispr")
        assert f"Open access — PDF (feed to read_pdf): {_PDF}" in result

    def test_open_access_without_pdf_says_open_access(self):
        r = _result(isOpenAccess="Y")  # no usable pdf entry
        with patch(PATCH, return_value=_ok(_search([r]))):
            result = search_europepmc("crispr")
        assert "Open access" in result
        assert "feed to read_pdf" not in result

    def test_paywalled_withholds_pdf(self):
        with patch(PATCH, return_value=_ok(_search([_result(isOpenAccess="N")]))):
            result = search_europepmc("crispr")
        assert "Subscription required — no open PDF" in result
        assert "read_pdf" not in result

    def test_renders_core_fields(self):
        with patch(PATCH, return_value=_ok(_search([_result()], hit=42))):
            result = search_europepmc("crispr")
        assert "Found 42 papers" in result
        assert "A paper" in result
        assert "Nature · 2026" in result
        assert "DOI: 10.1/x" in result

    def test_author_truncation(self):
        long_authors = ", ".join(f"Author{i} X" for i in range(40))
        with patch(PATCH, return_value=_ok(_search([_result(authorString=long_authors)]))):
            result = search_europepmc("x")
        assert "et al." in result

    def test_wrapped_untrusted(self):
        with patch(PATCH, return_value=_ok(_search([_result()]))):
            assert search_europepmc("x").startswith("[untrusted Europe PMC")

    def test_no_results(self):
        with patch(PATCH, return_value=_ok(_search([]))):
            assert "No papers found" in search_europepmc("zzzqwerty")

    def test_empty_query(self):
        assert "Provide a search query" in search_europepmc("  ")

    def test_max_results_clamped(self):
        with patch(PATCH, return_value=_ok(_search([_result()]))) as g:
            search_europepmc("x", max_results=999)
        assert g.call_args[1]["params"]["pageSize"] == 25

    def test_non_numeric_max_results_graceful(self):
        with patch(PATCH, side_effect=AssertionError("network must not be hit")):
            assert "Invalid max_results" in search_europepmc("x", max_results="abc")  # type: ignore[arg-type]

    def test_non_dict_result_skipped(self):
        with patch(PATCH, return_value=_ok(_search([_result(title="ok"), "not-a-dict"]))):
            result = search_europepmc("x")
        assert "ok" in result
        assert "(showing 1)" in result

    def test_only_non_dict_results_is_no_results(self):
        with patch(PATCH, return_value=_ok(_search(["not-a-dict"]))):
            assert "No papers found" in search_europepmc("x")

    def test_transport_failure_graceful(self):
        with patch(PATCH, side_effect=requests.ConnectionError("boom")):
            assert "Could not reach" in search_europepmc("x")


@pytest.mark.integration
def test_live_europepmc_open_access():
    result = search_europepmc("CRISPR AND OPEN_ACCESS:Y", max_results=3)
    assert result.startswith("[untrusted Europe PMC")
    assert "read_pdf" in result  # at least one OA paper should expose a PDF
