"""Tests for search_indicators and get_country_indicator (World Bank)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from openresearch_mcp.tools.worldbank import get_country_indicator, search_indicators

PATCH = "openresearch_mcp.http.requests.get"


def _ok(data) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = data
    r.raise_for_status.return_value = None
    return r


def _catalog(names: list[tuple[str, str]]) -> list:
    meta = {"page": 1, "pages": 1, "per_page": "2000", "total": len(names)}
    rows = [{"id": code, "name": name} for code, name in names]
    return [meta, rows]


def _series(rows: list[tuple[str, float | None]], *, indicator="GDP (current US$)", country="United States") -> list:
    meta = {"total": len(rows)}
    data_rows = [
        {
            "indicator": {"id": "NY.GDP.MKTP.CD", "value": indicator},
            "country": {"id": "US", "value": country},
            "countryiso3code": "USA",
            "date": date,
            "value": value,
        }
        for date, value in rows
    ]
    return [meta, data_rows]


_WB_ERROR = [{"message": [{"id": "120", "key": "Invalid value", "value": "The provided parameter value is not valid"}]}]


class TestSearchIndicators:
    def test_keyword_match(self):
        cat = _catalog([("SM.POP.NETM", "Net migration"), ("NY.GDP.MKTP.CD", "GDP (current US$)")])
        with patch(PATCH, return_value=_ok(cat)):
            result = search_indicators("migration")
        assert "SM.POP.NETM — Net migration" in result
        assert "GDP" not in result

    def test_token_and_semantics(self):
        cat = _catalog([
            ("SP.DYN.LE00.IN", "Life expectancy at birth, total (years)"),
            ("SM.POP.NETM", "Net migration"),
        ])
        with patch(PATCH, return_value=_ok(cat)):
            result = search_indicators("life expectancy")
        assert "SP.DYN.LE00.IN" in result
        assert "SM.POP.NETM" not in result

    def test_no_match(self):
        with patch(PATCH, return_value=_ok(_catalog([("X", "Something")]))):
            assert "No WDI indicators match" in search_indicators("zzzzz")

    def test_empty_query(self):
        assert "Provide a search keyword" in search_indicators("   ")

    def test_wrapped_untrusted(self):
        with patch(PATCH, return_value=_ok(_catalog([("SM.POP.NETM", "Net migration")]))):
            result = search_indicators("migration")
        assert result.startswith("[untrusted World Bank indicators")

    def test_results_capped(self):
        cat = _catalog([(f"CODE.{i}", f"GDP variant {i}") for i in range(40)])
        with patch(PATCH, return_value=_ok(cat)):
            result = search_indicators("gdp")
        assert "and 15 more" in result  # 40 matches, cap 25

    def test_row_missing_id_is_skipped_not_crashed(self):
        # A malformed catalog row (name but no id) must not KeyError — @tool_safe
        # would not catch it. It is skipped; the well-formed row still matches.
        cat = _catalog([("SM.POP.NETM", "Net migration")])
        cat[1].append({"name": "Migration something with no id"})  # missing "id"
        with patch(PATCH, return_value=_ok(cat)):
            result = search_indicators("migration")
        assert "SM.POP.NETM — Net migration" in result
        assert "no id" not in result

    def test_catalog_cached_across_calls(self):
        cat = _catalog([("SM.POP.NETM", "Net migration")])
        with patch(PATCH, return_value=_ok(cat)) as g:
            search_indicators("migration")
            search_indicators("migration")
        assert g.call_count == 1  # second served from cache_ttl


class TestGetCountryIndicator:
    def test_success_sorted_oldest_first(self):
        series = _series([("2021", 23315080560000), ("2019", 21380976119000), ("2020", 21060473613000)])
        with patch(PATCH, return_value=_ok(series)):
            result = get_country_indicator("United States", "NY.GDP.MKTP.CD")
        assert "GDP (current US$) — United States:" in result
        # ascending order: 2019 line appears before 2021 line
        assert result.index("2019:") < result.index("2020:") < result.index("2021:")

    def test_null_values_filtered(self):
        series = _series([("2022", None), ("2021", 100.0)])
        with patch(PATCH, return_value=_ok(series)):
            result = get_country_indicator("Germany", "NY.GDP.MKTP.CD")
        assert "2021: 100.0" in result
        assert "2022:" not in result

    def test_invalid_country_before_network(self):
        with patch(PATCH, side_effect=AssertionError("network must not be hit")):
            result = get_country_indicator("Atlantis", "NY.GDP.MKTP.CD")
        assert "Invalid country" in result

    def test_inverted_year_range_before_network(self):
        with patch(PATCH, side_effect=AssertionError("network must not be hit")):
            result = get_country_indicator("US", "NY.GDP.MKTP.CD", start=2020, end=2010)
        assert "Invalid year range" in result

    def test_year_range_param_built(self):
        with patch(PATCH, return_value=_ok(_series([("2010", 1.0)]))) as g:
            get_country_indicator("US", "NY.GDP.MKTP.CD", start=2000, end=2020)
        assert g.call_args[1]["params"]["date"] == "2000:2020"

    def test_worldbank_error_payload(self):
        with patch(PATCH, return_value=_ok(_WB_ERROR)):
            result = get_country_indicator("US", "BOGUS.CODE")
        assert "World Bank error" in result
        assert "search_indicators" in result

    def test_no_rows(self):
        with patch(PATCH, return_value=_ok([{"total": 0}, None])):
            result = get_country_indicator("US", "NY.GDP.MKTP.CD")
        assert "No data" in result

    def test_transport_failure_graceful(self):
        with patch(PATCH, side_effect=requests.ConnectionError("boom")):
            result = get_country_indicator("US", "NY.GDP.MKTP.CD")
        assert "Could not reach" in result

    def test_wrapped_untrusted(self):
        with patch(PATCH, return_value=_ok(_series([("2021", 1.0)]))):
            result = get_country_indicator("US", "NY.GDP.MKTP.CD")
        assert result.startswith("[untrusted World Bank")


@pytest.mark.integration
def test_live_search_indicators():
    result = search_indicators("net migration")
    assert "SM.POP.NETM" in result
    assert result.startswith("[untrusted World Bank indicators")


@pytest.mark.integration
def test_live_country_indicator():
    result = get_country_indicator("Germany", "SP.POP.TOTL", start=2018, end=2021)
    assert "Germany" in result
    assert "2018:" in result and "2021:" in result
    assert result.startswith("[untrusted World Bank")
