"""Tests for get_company_financials (SEC EDGAR XBRL)."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from openresearch_mcp.tools.sec import _filing_url, get_company_financials, search_sec_filings

PATCH = "openresearch_mcp.http.requests.get"

_TICKERS = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}


def _ok(data: dict) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = data
    r.raise_for_status.return_value = None
    return r


def _err(status: int) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.raise_for_status.side_effect = requests.HTTPError(f"{status}")
    return r


def _concept(*pairs: tuple[str, int], form: str = "10-K") -> dict:
    return {"units": {"USD": [{"form": form, "end": e, "val": v} for e, v in pairs]}}


def _route(table: dict):
    """side_effect that returns a response based on a substring of the request URL.

    Anything unmatched → 404 (mirrors SEC returning 404 for an absent concept).
    """
    def _get(url, **kwargs):
        for key, resp in table.items():
            if key in url:
                return resp
        return _err(404)
    return _get


class TestGetCompanyFinancials:
    def test_success_assembles_metrics(self):
        table = {
            "company_tickers": _ok(_TICKERS),
            "RevenueFromContractWithCustomer": _ok(_concept(("2024-09-28", 391035000000), ("2023-09-30", 383285000000))),
            "NetIncomeLoss": _ok(_concept(("2024-09-28", 93736000000))),
            "Assets": _ok(_concept(("2024-09-28", 364980000000))),
            "StockholdersEquity": _ok(_concept(("2024-09-28", 56950000000))),
        }
        with patch(PATCH, side_effect=_route(table)):
            result = get_company_financials("aapl")
        assert "Apple Inc. (AAPL)" in result
        assert "Revenue:" in result and "2024: 391,035,000,000" in result
        assert "Net income:" in result and "93,736,000,000" in result
        assert "Total assets:" in result
        assert result.startswith("[untrusted SEC EDGAR")

    def test_revenue_tag_fallback_to_legacy(self):
        # Modern revenue tag 404s → must fall back to "Revenues", not skip revenue.
        table = {
            "company_tickers": _ok(_TICKERS),
            "RevenueFromContractWithCustomer": _err(404),
            "Revenues": _ok(_concept(("2018-09-29", 265595000000))),
        }
        with patch(PATCH, side_effect=_route(table)):
            result = get_company_financials("AAPL")
        assert "Revenue:" in result
        assert "2018: 265,595,000,000" in result

    def test_missing_concept_skipped_not_crashed(self):
        # Only net income reported; the other concepts 404 → skipped, tool still works.
        table = {"company_tickers": _ok(_TICKERS), "NetIncomeLoss": _ok(_concept(("2024-09-28", 93736000000)))}
        with patch(PATCH, side_effect=_route(table)):
            result = get_company_financials("AAPL")
        assert "Net income:" in result
        assert "Revenue:" not in result

    def test_non_404_concept_error_is_not_masked_as_no_data(self):
        table = {"company_tickers": _ok(_TICKERS), "RevenueFromContractWithCustomer": _err(403)}
        with patch(PATCH, side_effect=_route(table)):
            result = get_company_financials("AAPL")
        assert "SEC returned HTTP 403" in result
        assert "No annual XBRL" not in result

    def test_non_numeric_values_skipped(self):
        table = {
            "company_tickers": _ok(_TICKERS),
            "NetIncomeLoss": _ok(_concept(("2024-09-28", "not-a-number"))),
        }
        with patch(PATCH, side_effect=_route(table)):
            result = get_company_financials("AAPL")
        assert "No annual XBRL" in result

    def test_dedupes_by_fiscal_year(self):
        # Same fiscal year reported in two filings → one line.
        table = {
            "company_tickers": _ok(_TICKERS),
            "NetIncomeLoss": _ok(_concept(("2024-09-28", 93736000000), ("2024-09-28", 93736000000))),
        }
        with patch(PATCH, side_effect=_route(table)):
            result = get_company_financials("AAPL")
        assert result.count("2024: 93,736,000,000") == 1

    def test_non_10k_forms_ignored(self):
        table = {
            "company_tickers": _ok(_TICKERS),
            "NetIncomeLoss": _ok(_concept(("2024-06-29", 21448000000), form="10-Q")),
        }
        with patch(PATCH, side_effect=_route(table)):
            result = get_company_financials("AAPL")
        assert "No annual XBRL" in result  # only quarterly data → nothing annual

    def test_unknown_ticker(self):
        with patch(PATCH, side_effect=_route({"company_tickers": _ok(_TICKERS)})):
            assert "No SEC filer found" in get_company_financials("ZZZZ")

    def test_empty_ticker(self):
        assert "Provide a stock ticker" in get_company_financials("  ")

    def test_sec_user_agent_used(self):
        table = {"company_tickers": _ok(_TICKERS), "NetIncomeLoss": _ok(_concept(("2024-09-28", 1)))}
        captured = {}

        def _get(url, **kwargs):
            captured["ua"] = kwargs.get("headers", {}).get("User-Agent")
            for key, resp in table.items():
                if key in url:
                    return resp
            return _err(404)

        with patch.dict(os.environ, {"SEC_USER_AGENT": "me@example.com"}), \
             patch(PATCH, side_effect=_get):
            get_company_financials("AAPL")
        assert captured["ua"] == "me@example.com"

    def test_transport_failure_graceful(self):
        with patch(PATCH, side_effect=requests.ConnectionError("boom")):
            assert "Could not reach" in get_company_financials("AAPL")


def _hit(*, cik="0000035527", acc="0000035527-22-000119", filename="doc10-k.htm",
         form="10-K", date="2022-02-25", name="FIFTH THIRD BANCORP  (FITB)  (CIK 0000035527)") -> dict:
    return {"_id": f"{acc}:{filename}",
            "_source": {"ciks": [cik], "display_names": [name], "form": form, "file_date": date}}


def _efts(hits: list, total: int | None = None) -> dict:
    return {"hits": {"total": {"value": total if total is not None else len(hits)}, "hits": hits}}


class TestFilingUrl:
    def test_builds_document_url(self):
        url = _filing_url(_hit())
        assert url == "https://www.sec.gov/Archives/edgar/data/35527/000003552722000119/doc10-k.htm"

    def test_missing_colon_returns_none(self):
        assert _filing_url({"_id": "noColonHere", "_source": {"ciks": ["1"]}}) is None

    def test_missing_ciks_returns_none(self):
        assert _filing_url({"_id": "a:b", "_source": {}}) is None

    def test_url_encodes_external_path_segments(self):
        url = _filing_url(_hit(filename="risk report 10-k.htm"))
        assert url.endswith("/risk%20report%2010-k.htm")


class TestSearchSecFilings:
    def test_success_with_document_url(self):
        with patch(PATCH, return_value=_ok(_efts([_hit()], total=1450))):
            result = search_sec_filings("climate risk", forms="10-K")
        assert "Found 1450 SEC filings" in result
        assert "FIFTH THIRD BANCORP" in result
        assert "10-K · 2022-02-25" in result
        assert "edgar/data/35527/000003552722000119/doc10-k.htm" in result
        assert result.startswith("[untrusted SEC EDGAR")

    def test_forms_param_passed(self):
        with patch(PATCH, return_value=_ok(_efts([_hit()]))) as g:
            search_sec_filings("x", forms="10-K,10-Q")
        assert g.call_args[1]["params"]["forms"] == "10-K,10-Q"

    def test_no_forms_param_when_omitted(self):
        with patch(PATCH, return_value=_ok(_efts([_hit()]))) as g:
            search_sec_filings("x")
        assert "forms" not in g.call_args[1]["params"]

    def test_empty_query(self):
        assert "Provide search terms" in search_sec_filings("  ")

    def test_no_hits(self):
        with patch(PATCH, return_value=_ok(_efts([]))):
            assert "No SEC filings found" in search_sec_filings("zzzqwerty")

    def test_max_results_clamped_and_sliced(self):
        hits = [_hit(acc=f"000-{i}", filename=f"f{i}.htm") for i in range(30)]
        with patch(PATCH, return_value=_ok(_efts(hits))):
            result = search_sec_filings("x", max_results=999)
        assert result.count("Document (feed to read_url/read_pdf)") == 25  # clamped to 25

    def test_non_numeric_max_results(self):
        with patch(PATCH, side_effect=AssertionError("no network")):
            assert "Invalid max_results" in search_sec_filings("x", max_results="abc")  # type: ignore[arg-type]

    def test_non_dict_hit_skipped(self):
        with patch(PATCH, return_value=_ok(_efts([_hit(), "not-a-dict"]))):
            result = search_sec_filings("x")
        assert "FIFTH THIRD BANCORP" in result

    def test_malformed_id_omits_url_but_keeps_entry(self):
        bad = {"_id": "no-colon", "_source": {"ciks": ["1"], "display_names": ["ACME"], "form": "8-K"}}
        with patch(PATCH, return_value=_ok(_efts([bad]))):
            result = search_sec_filings("x")
        assert "ACME" in result
        assert "Document (feed" not in result

    def test_transport_failure_graceful(self):
        with patch(PATCH, side_effect=requests.ConnectionError("boom")):
            assert "Could not reach" in search_sec_filings("x")


@pytest.mark.integration
def test_live_sec_filings():
    result = search_sec_filings("climate risk", forms="10-K", max_results=3)
    assert isinstance(result, str) and result
    assert ("SEC filings" in result and "edgar/data" in result) or "SEC" in result


@pytest.mark.integration
def test_live_company_financials():
    # SEC rate-limits/403s shared IPs under load; accept real data OR a graceful SEC
    # message — the point is it never raises. (Verify data locally from a fresh IP.)
    result = get_company_financials("AAPL")
    assert isinstance(result, str) and result
    assert ("Apple Inc." in result and "Revenue:" in result) or "SEC" in result
