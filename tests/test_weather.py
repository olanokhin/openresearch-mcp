"""Tests for get_weather_forecast and its _geocode helper."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from openresearch_mcp.tools.weather import (
    _describe_code,
    get_historical_weather,
    get_weather_forecast,
)

PATCH = "openresearch_mcp.http.requests.get"


def _ok(data: dict) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = data
    r.raise_for_status.return_value = None
    return r


def _geo(**over) -> dict:
    base = {"name": "Berlin", "latitude": 52.52, "longitude": 13.41, "country": "Germany"}
    return {"results": [{**base, **over}]}


def _forecast() -> dict:
    return {
        "current": {
            "time": "2026-06-28T12:00", "temperature_2m": 22.5,
            "relative_humidity_2m": 55, "weather_code": 1, "wind_speed_10m": 12.0,
        },
        "daily": {
            "time": ["2026-06-28", "2026-06-29"],
            "weather_code": [1, 61],
            "temperature_2m_max": [25.0, 20.0],
            "temperature_2m_min": [15.0, 12.0],
            "precipitation_sum": [0.0, 5.2],
        },
    }


class TestDescribeCode:
    def test_known_code(self):
        assert _describe_code(0) == "Clear sky"

    def test_unknown_code_is_labelled(self):
        assert _describe_code(123) == "code 123"

    def test_non_numeric_is_safe(self):
        assert _describe_code(None) == "code None"


class TestGetWeatherForecast:
    def test_success_renders_current_and_daily(self):
        with patch(PATCH, side_effect=[_ok(_geo()), _ok(_forecast())]):
            result = get_weather_forecast("Berlin")
        assert "Berlin, Germany" in result
        assert "22.5°C" in result
        assert "Mainly clear" in result      # current weather_code 1
        assert "Slight rain" in result        # daily weather_code 61
        assert "precip 5.2 mm" in result
        assert "15.0–25.0°C" in result

    def test_wrapped_as_untrusted(self):
        with patch(PATCH, side_effect=[_ok(_geo()), _ok(_forecast())]):
            result = get_weather_forecast("Berlin")
        assert result.startswith("[untrusted weather forecast")

    def test_location_not_found_skips_forecast_call(self):
        # Geocoding miss → friendly message, and the forecast endpoint is NOT hit.
        with patch(PATCH, side_effect=[_ok({"results": []})]) as g:
            result = get_weather_forecast("Xyzzyland")
        assert "Could not find" in result
        assert g.call_count == 1  # only geocoding was called

    def test_days_clamped_to_16(self):
        with patch(PATCH, side_effect=[_ok(_geo()), _ok(_forecast())]) as g:
            get_weather_forecast("Berlin", days=999)
        forecast_call = g.call_args_list[1]
        assert forecast_call[1]["params"]["forecast_days"] == 16

    def test_open_meteo_error_body_handled(self):
        err = {"error": True, "reason": "Latitude must be in range"}
        with patch(PATCH, side_effect=[_ok(_geo()), _ok(err)]):
            result = get_weather_forecast("Berlin")
        assert "Weather service error" in result
        assert "Latitude must be in range" in result

    def test_transport_failure_returns_graceful_string(self):
        with patch(PATCH, side_effect=requests.ConnectionError("boom")):
            result = get_weather_forecast("Berlin")
        assert "Could not reach" in result  # SourceError public message via @tool_safe

    def test_mismatched_daily_arrays_do_not_crash(self):
        # Open-Meteo returns 2 dates but a truncated codes/precip array. Must render
        # with "N/A" rather than raising IndexError (which @tool_safe would NOT catch).
        broken = _forecast()
        broken["daily"]["weather_code"] = [1]          # only 1 of 2
        broken["daily"]["precipitation_sum"] = []      # none
        with patch(PATCH, side_effect=[_ok(_geo()), _ok(broken)]):
            result = get_weather_forecast("Berlin")
        assert "2026-06-29" in result  # second day still listed
        assert "N/A" in result


def _archive(**daily) -> dict:
    base = {
        "time": ["2020-01-01", "2020-01-02", "2020-02-01"],
        "temperature_2m_mean": [5.0, 7.0, 10.0],
        "precipitation_sum": [2.0, 0.0, 5.0],
    }
    return {"daily": {**base, **daily}}


class TestGetHistoricalWeather:
    def test_monthly_aggregation(self):
        with patch(PATCH, side_effect=[_ok(_geo()), _ok(_archive())]):
            result = get_historical_weather("Berlin", "2020-01-01", "2020-02-29")
        assert "aggregated monthly" in result
        assert "2020-01: mean temp 6.0°C, precip 2.0 mm" in result   # (5+7)/2, 2+0
        assert "2020-02: mean temp 10.0°C, precip 5.0 mm" in result

    def test_yearly_aggregation(self):
        with patch(PATCH, side_effect=[_ok(_geo()), _ok(_archive())]):
            result = get_historical_weather("Berlin", "2020-01-01", "2020-12-31", aggregate="yearly")
        assert "aggregated yearly" in result
        assert "2020: mean temp 7.3°C, precip 7.0 mm" in result       # (5+7+10)/3, 2+0+5

    def test_wrapped_as_untrusted(self):
        with patch(PATCH, side_effect=[_ok(_geo()), _ok(_archive())]):
            result = get_historical_weather("Berlin", "2020-01-01", "2020-02-29")
        assert result.startswith("[untrusted historical weather")

    def test_nulls_are_skipped_not_zeroed(self):
        archive = _archive(temperature_2m_mean=[5.0, None, 9.0], precipitation_sum=[2.0, None, 4.0])
        with patch(PATCH, side_effect=[_ok(_geo()), _ok(archive)]):
            result = get_historical_weather("Berlin", "2020-01-01", "2020-02-29")
        # Jan: only 5.0 counts for temp (None skipped) → mean 5.0; precip 2.0 (None skipped)
        assert "2020-01: mean temp 5.0°C, precip 2.0 mm" in result

    def test_invalid_aggregate_rejected_before_network(self):
        with patch(PATCH, side_effect=AssertionError("network must not be hit")):
            result = get_historical_weather("Berlin", "2020-01-01", "2020-02-01", aggregate="weekly")
        assert "Unknown aggregate" in result

    def test_inverted_range_rejected_before_network(self):
        with patch(PATCH, side_effect=AssertionError("network must not be hit")):
            result = get_historical_weather("Berlin", "2020-12-31", "2020-01-01")
        assert "Invalid date range" in result
        assert "after end" in result

    def test_location_not_found_skips_archive_call(self):
        with patch(PATCH, side_effect=[_ok({"results": []})]) as g:
            result = get_historical_weather("Xyzzyland", "2020-01-01", "2020-02-01")
        assert "Could not find" in result
        assert g.call_count == 1

    def test_empty_data_handled(self):
        with patch(PATCH, side_effect=[_ok(_geo()), _ok({"daily": {"time": []}})]):
            result = get_historical_weather("Berlin", "2020-01-01", "2020-02-01")
        assert "No historical data" in result

    def test_transport_failure_returns_graceful_string(self):
        with patch(PATCH, side_effect=requests.ConnectionError("boom")):
            result = get_historical_weather("Berlin", "2020-01-01", "2020-02-01")
        assert "Could not reach" in result


@pytest.mark.integration
def test_live_open_meteo_forecast():
    """Hits real Open-Meteo (geocoding + forecast) to confirm param/response shape.

    Marked integration → excluded from the gating CI job; run with `-m integration`.
    """
    result = get_weather_forecast("Berlin", days=3)
    if result.startswith("Could not reach Open-Meteo"):
        return
    assert "Berlin" in result
    assert "°C" in result
    assert "Forecast (3 days)" in result
    assert result.startswith("[untrusted weather forecast")


@pytest.mark.integration
def test_live_open_meteo_archive():
    """Hits the real Open-Meteo archive host to confirm param/response shape."""
    result = get_historical_weather("Berlin", "2020-01-01", "2021-12-31", aggregate="yearly")
    if result.startswith("Could not reach Open-Meteo"):
        return
    assert "Berlin" in result
    assert "aggregated yearly" in result
    assert "2020:" in result and "2021:" in result
    assert result.startswith("[untrusted historical weather")
