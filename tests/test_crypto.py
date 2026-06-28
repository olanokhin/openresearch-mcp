"""Tests for get_crypto_price (CoinGecko, keyless)."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from openresearch_mcp.tools.crypto import _coin_id, get_crypto_price

PATCH = "openresearch_mcp.http.requests.get"


def _ok(data: dict) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = data
    r.raise_for_status.return_value = None
    return r


def _ms(y: int, m: int, d: int, h: int = 0) -> int:
    return int(datetime(y, m, d, h, tzinfo=UTC).timestamp() * 1000)


class TestCoinId:
    def test_symbol_mapped(self):
        assert _coin_id("btc") == "bitcoin"
        assert _coin_id("ETH") == "ethereum"

    def test_full_name_passes_through(self):
        assert _coin_id("Bitcoin") == "bitcoin"
        assert _coin_id("solana") == "solana"


class TestCurrentPrice:
    def test_success(self):
        with patch(PATCH, return_value=_ok({"bitcoin": {"usd": 60009}})):
            result = get_crypto_price("bitcoin")
        assert "bitcoin: 60009.00 USD" in result
        assert result.startswith("[untrusted crypto price")

    def test_symbol_normalized_in_request(self):
        with patch(PATCH, return_value=_ok({"bitcoin": {"usd": 1}})) as g:
            get_crypto_price("btc")
        assert g.call_args[1]["params"]["ids"] == "bitcoin"

    def test_unknown_coin_empty_object(self):
        # CoinGecko returns {} (HTTP 200) for an unknown id — must be a friendly message.
        with patch(PATCH, return_value=_ok({})):
            assert "No price for" in get_crypto_price("notacoin")

    def test_empty_input(self):
        assert "Provide a coin" in get_crypto_price("  ")

    def test_transport_failure_graceful(self):
        import requests
        with patch(PATCH, side_effect=requests.ConnectionError("boom")):
            assert "Could not reach" in get_crypto_price("bitcoin")


class TestHistory:
    def _chart(self) -> dict:
        return {"prices": [
            [_ms(2024, 1, 1, 0), 42000.0],
            [_ms(2024, 1, 1, 12), 42500.0],   # later same day → wins
            [_ms(2024, 1, 2, 0), 43000.0],
        ]}

    def test_daily_downsample_last_per_day(self):
        with patch(PATCH, return_value=_ok(self._chart())):
            result = get_crypto_price("bitcoin", days=2)
        assert "last 2 days (daily)" in result
        assert "2024-01-01: 42500.00" in result   # 12:00 value, not 00:00
        assert "2024-01-02: 43000.00" in result

    def test_days_clamped(self):
        with patch(PATCH, return_value=_ok(self._chart())) as g:
            get_crypto_price("bitcoin", days=9999)
        assert g.call_args[1]["params"]["days"] == 365

    def test_malformed_points_skipped(self):
        chart = {"prices": [[_ms(2024, 1, 1), 100.0], ["bad"], [None, None]]}
        with patch(PATCH, return_value=_ok(chart)):
            result = get_crypto_price("bitcoin", days=2)
        assert "2024-01-01: 100.00" in result

    def test_no_history(self):
        with patch(PATCH, return_value=_ok({"prices": []})):
            assert "No price history" in get_crypto_price("bitcoin", days=7)

    def test_non_numeric_days_is_graceful(self):
        # A client passing days="abc" must not ValueError past @tool_safe.
        with patch(PATCH, side_effect=AssertionError("network must not be hit")):
            result = get_crypto_price("bitcoin", days="abc")  # type: ignore[arg-type]
        assert "Invalid days" in result


class TestPriceFormatting:
    def test_rounds_to_two_decimals(self):
        with patch(PATCH, return_value=_ok({"bitcoin": {"usd": 1662.7223086936242}})):
            assert "bitcoin: 1662.72 USD" in get_crypto_price("bitcoin")

    def test_whole_number_gets_two_decimals(self):
        with patch(PATCH, return_value=_ok({"bitcoin": {"usd": 60000}})):
            assert "60000.00 USD" in get_crypto_price("bitcoin")

    def test_sub_cent_keeps_significant_digits(self):
        # SHIB-like micro price must NOT collapse to 0.00.
        with patch(PATCH, return_value=_ok({"shiba-inu": {"usd": 0.00001234}})):
            result = get_crypto_price("shib")
        assert "0.00001234" in result
        assert ": 0.00 USD" not in result


class TestVsCurrency:
    def test_nonstandard_vs_passed_through(self):
        with patch(PATCH, return_value=_ok({"bitcoin": {"eur": 55000}})) as g:
            result = get_crypto_price("bitcoin", vs="eur")
        assert g.call_args[1]["params"]["vs_currencies"] == "eur"
        assert "55000.00 EUR" in result

    def test_unsupported_vs_is_graceful(self):
        # Coin present but quote missing (CoinGecko drops an unknown vs) → friendly, no crash.
        with patch(PATCH, return_value=_ok({"bitcoin": {}})):
            assert "No price for" in get_crypto_price("bitcoin", vs="zzz")


class TestThrottleCacheConsumer:
    def test_repeated_call_served_from_cache(self):
        # First real consumer of fetch_json's cache_ttl: a re-ask hits cache, not network.
        with patch(PATCH, return_value=_ok({"bitcoin": {"usd": 1}})) as g:
            get_crypto_price("bitcoin")
            get_crypto_price("bitcoin")
        assert g.call_count == 1


@pytest.mark.integration
def test_live_crypto_current():
    result = get_crypto_price("bitcoin", vs="usd")
    assert "bitcoin:" in result
    assert "USD" in result
    assert result.startswith("[untrusted crypto price")


@pytest.mark.integration
def test_live_crypto_history():
    result = get_crypto_price("ethereum", vs="usd", days=7)
    assert "ethereum in USD" in result
    assert result.startswith("[untrusted crypto price")
