"""Tests for get_fx_rate (Frankfurter / ECB)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from openresearch_mcp.tools.fx import get_fx_rate

PATCH = "openresearch_mcp.http.requests.get"


def _ok(data: dict) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = data
    r.raise_for_status.return_value = None
    return r


def _http_error(status: int) -> MagicMock:
    import requests
    r = MagicMock()
    r.status_code = status
    r.raise_for_status.side_effect = requests.HTTPError(f"{status}")
    return r


_LATEST = {"amount": 1.0, "base": "USD", "date": "2026-06-26", "rates": {"EUR": 0.877, "GBP": 0.756}}
_SERIES = {
    "amount": 1.0, "base": "USD", "start_date": "2020-01-02", "end_date": "2020-02-28",
    "rates": {
        "2020-01-02": {"EUR": 0.89}, "2020-01-31": {"EUR": 0.90},
        "2020-02-03": {"EUR": 0.91}, "2020-02-28": {"EUR": 0.92},
    },
}


class TestGetFxRate:
    def test_latest(self):
        with patch(PATCH, return_value=_ok(_LATEST)):
            result = get_fx_rate("EUR,GBP")
        assert "USD → EUR,GBP (as of 2026-06-26)" in result
        assert "EUR 0.877" in result and "GBP 0.756" in result

    def test_single_historical_date(self):
        point = {"amount": 1.0, "base": "USD", "date": "2020-03-13", "rates": {"EUR": 0.90}}
        with patch(PATCH, return_value=_ok(point)) as g:
            result = get_fx_rate("EUR", start="2020-03-15")
        assert "as of 2020-03-13" in result
        assert "2020-03-15" in g.call_args[0][0]  # single-date path in URL

    def test_series(self):
        with patch(PATCH, return_value=_ok(_SERIES)) as g:
            result = get_fx_rate("EUR", start="2020-01-01", end="2020-02-29")
        assert "2020-01-02..2020-02-28 (4 points)" in result
        assert "2020-01-02: EUR 0.89" in result
        assert ".." in g.call_args[0][0]  # range path in URL

    def test_series_downsampled_monthly(self):
        with patch(PATCH, return_value=_ok(_SERIES)):
            result = get_fx_rate("EUR", start="2020-01-01", end="2020-02-29", group="month")
        assert "2 points, month" in result
        assert "2020-01-31: EUR" in result and "2020-02-28: EUR" in result  # last per month
        assert "2020-01-02: EUR" not in result                              # earlier obs dropped

    def test_base_and_symbols_normalized(self):
        # First real consumer of normalize_currency: "euro"/"pound" → ISO codes.
        with patch(PATCH, return_value=_ok(_LATEST)) as g:
            get_fx_rate("pound", base="euro")
        params = g.call_args[1]["params"]
        assert params["base"] == "EUR"
        assert params["symbols"] == "GBP"

    def test_invalid_base_before_network(self):
        with patch(PATCH, side_effect=AssertionError("network must not be hit")):
            assert "Invalid base currency" in get_fx_rate("EUR", base="ZZZ")

    def test_invalid_symbol_before_network(self):
        with patch(PATCH, side_effect=AssertionError("network must not be hit")):
            assert "Invalid symbol currency" in get_fx_rate("LOL", base="USD")

    def test_invalid_group_before_network(self):
        with patch(PATCH, side_effect=AssertionError("network must not be hit")):
            assert "Unknown group" in get_fx_rate("EUR", start="2020-01-01", end="2020-02-01", group="daily")

    def test_inverted_range_before_network(self):
        with patch(PATCH, side_effect=AssertionError("network must not be hit")):
            assert "Invalid date" in get_fx_rate("EUR", start="2020-12-31", end="2020-01-01")

    def test_wrapped_untrusted(self):
        with patch(PATCH, return_value=_ok(_LATEST)):
            assert get_fx_rate("EUR").startswith("[untrusted FX rates")

    def test_unsupported_currency_404_is_graceful(self):
        # Valid ISO code Frankfurter doesn't track → 404 → SourceError via @tool_safe.
        with patch(PATCH, return_value=_http_error(404)):
            result = get_fx_rate("XAU")  # gold, valid ISO-4217, not an ECB rate
        assert "Frankfurter (ECB)" in result and "404" in result


class TestDateBehaviour:
    def test_latest_surfaces_api_date_not_today(self):
        # Weekend/holiday: ECB publishes only business days, so "latest" returns the
        # last business day. The tool must surface that date, not fabricate "today".
        friday = {"amount": 1.0, "base": "USD", "date": "2026-06-26", "rates": {"EUR": 0.877}}
        with patch(PATCH, return_value=_ok(friday)):
            result = get_fx_rate("EUR")
        assert "as of 2026-06-26" in result

    def test_single_date_uses_returned_date_after_ecb_snap(self):
        # Requested a non-business day; API snapped to the prior business day. The
        # rendered "as of" must be the returned date, not the requested one.
        snapped = {"amount": 1.0, "base": "USD", "date": "2020-03-13", "rates": {"EUR": 0.90}}
        with patch(PATCH, return_value=_ok(snapped)):
            result = get_fx_rate("EUR", start="2020-03-15")  # a Sunday
        assert "as of 2020-03-13" in result
        assert "as of 2020-03-15" not in result


class TestDownsampling:
    def test_weekly_keeps_last_per_iso_week(self):
        series = {
            "amount": 1.0, "base": "USD", "start_date": "2024-01-01", "end_date": "2024-01-08",
            "rates": {
                "2024-01-01": {"EUR": 1.0}, "2024-01-03": {"EUR": 2.0},  # ISO week 1
                "2024-01-08": {"EUR": 3.0},                              # ISO week 2
            },
        }
        with patch(PATCH, return_value=_ok(series)):
            result = get_fx_rate("EUR", start="2024-01-01", end="2024-01-08", group="week")
        assert "2 points, week" in result
        assert "2024-01-03: EUR 2.0" in result and "2024-01-08: EUR 3.0" in result
        assert "2024-01-01: EUR" not in result

    def test_monthly_does_not_merge_across_years(self):
        # Dec 2023 and Jan 2024 must stay distinct buckets (key is YYYY-MM, not YYYY).
        series = {
            "amount": 1.0, "base": "USD", "start_date": "2023-12-29", "end_date": "2024-01-02",
            "rates": {
                "2023-12-29": {"EUR": 1.0}, "2023-12-31": {"EUR": 2.0},
                "2024-01-02": {"EUR": 3.0},
            },
        }
        with patch(PATCH, return_value=_ok(series)):
            result = get_fx_rate("EUR", start="2023-12-01", end="2024-01-31", group="month")
        assert "2 points, month" in result
        assert "2023-12-31: EUR 2.0" in result and "2024-01-02: EUR 3.0" in result


def test_huge_series_capped_to_max_text_chars():
    from openresearch_mcp.constants import MAX_TEXT_CHARS
    rates = {f"2020-{m:02d}-{d:02d}": {"EUR": 0.9} for m in range(1, 13) for d in range(1, 29)}
    big = {"amount": 1.0, "base": "USD", "start_date": "2020-01-01", "end_date": "2020-12-31", "rates": rates}
    with patch(PATCH, return_value=_ok(big)):
        result = get_fx_rate("EUR", start="2020-01-01", end="2020-12-31")
    body = result.split("\n\n", 1)[1]  # strip the untrusted-notice prefix
    assert len(body) <= MAX_TEXT_CHARS


@pytest.mark.integration
def test_live_fx_latest():
    result = get_fx_rate("EUR,GBP", base="USD")
    assert "USD → EUR,GBP" in result
    assert "EUR" in result
    assert result.startswith("[untrusted FX rates")


@pytest.mark.integration
def test_live_fx_series_monthly():
    result = get_fx_rate("EUR", base="USD", start="2020-01-01", end="2020-06-30", group="month")
    assert "month" in result
    assert result.startswith("[untrusted FX rates")
