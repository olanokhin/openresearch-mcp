"""Tests for the identifier-normalization gate (country/date/currency)."""
from __future__ import annotations

import pytest

from openresearch_mcp.identifiers import (
    normalize_country,
    normalize_currency,
    normalize_date,
    normalize_date_range,
    normalize_year,
)


class TestNormalizeCountry:
    @pytest.mark.parametrize("value,expected", [
        ("Germany", "DE"),
        ("germany", "DE"),
        ("  Germany  ", "DE"),
        ("DE", "DE"),
        ("de", "DE"),
        ("DEU", "DE"),
        ("USA", "US"),
        ("United States", "US"),
        ("uk", "GB"),
        ("Britain", "GB"),
        ("türkiye", "TR"),
        ("Afghanistan", "AF"),
        ("Aland Islands", "AX"),
        ("Cabo Verde", "CV"),
        ("Côte d'Ivoire", "CI"),
        ("Eswatini", "SZ"),
        ("Lao People's Democratic Republic", "LA"),
        ("Namibia", "NA"),
        ("RWA", "RW"),
        ("Zimbabwe", "ZW"),
    ])
    def test_normalizes_to_alpha2(self, value, expected):
        assert normalize_country(value) == expected

    def test_unknown_raises_with_guidance(self):
        with pytest.raises(ValueError, match="ISO-3166"):
            normalize_country("Atlantis")

    def test_bogus_two_letter_code_rejected(self):
        # A 2-letter string that is not a real code must not be echoed back.
        with pytest.raises(ValueError):
            normalize_country("ZZ")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            normalize_country("   ")


class TestNormalizeDate:
    @pytest.mark.parametrize("value,expected", [
        ("2026-06-28", "2026-06-28"),
        ("2026/06/28", "2026-06-28"),
        ("28.06.2026", "2026-06-28"),
        ("28/06/2026", "2026-06-28"),
        ("  2026-06-28 ", "2026-06-28"),
    ])
    def test_normalizes_to_iso(self, value, expected):
        assert normalize_date(value) == expected

    def test_accepts_date_object(self):
        from datetime import date
        assert normalize_date(date(2026, 6, 28)) == "2026-06-28"

    def test_accepts_datetime_object_drops_time(self):
        from datetime import datetime
        assert normalize_date(datetime(2026, 6, 28, 14, 30, 0)) == "2026-06-28"

    def test_invalid_date_raises(self):
        with pytest.raises(ValueError, match="ISO-8601"):
            normalize_date("2026-13-40")

    def test_error_lists_supported_formats(self):
        with pytest.raises(ValueError, match="DD.MM.YYYY"):
            normalize_date("not a date")


class TestNormalizeDateRange:
    def test_valid_range_returned_as_iso(self):
        assert normalize_date_range("2026-01-01", "2026-12-31") == ("2026-01-01", "2026-12-31")

    def test_equal_dates_allowed(self):
        assert normalize_date_range("2026-06-28", "2026-06-28") == ("2026-06-28", "2026-06-28")

    def test_mixed_formats_and_objects(self):
        from datetime import date
        assert normalize_date_range("01.01.2026", date(2026, 6, 28)) == ("2026-01-01", "2026-06-28")

    def test_inverted_range_raises(self):
        with pytest.raises(ValueError, match="after end"):
            normalize_date_range("2026-12-31", "2026-01-01")

    def test_invalid_member_raises(self):
        with pytest.raises(ValueError):
            normalize_date_range("garbage", "2026-01-01")


class TestNormalizeYear:
    @pytest.mark.parametrize("value,expected", [
        (2026, 2026), ("2026", 2026), ("  1999 ", 1999),
    ])
    def test_valid_year(self, value, expected):
        assert normalize_year(value) == expected

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError, match="range"):
            normalize_year(99)

    def test_non_numeric_raises(self):
        with pytest.raises(ValueError):
            normalize_year("twenty")


class TestNormalizeCurrency:
    @pytest.mark.parametrize("value,expected", [
        ("usd", "USD"), ("USD", "USD"), (" eur ", "EUR"),
        ("jpy", "JPY"), ("CHF", "CHF"),  # real ISO codes pass through
    ])
    def test_iso_codes(self, value, expected):
        assert normalize_currency(value) == expected

    @pytest.mark.parametrize("value,expected", [
        ("dollar", "USD"), ("US Dollar", "USD"),
        ("euro", "EUR"), ("pound", "GBP"), ("sterling", "GBP"),
        ("yen", "JPY"), ("yuan", "CNY"), ("renminbi", "CNY"), ("ruble", "RUB"),
    ])
    def test_human_aliases(self, value, expected):
        assert normalize_currency(value) == expected

    @pytest.mark.parametrize("bad", ["ZZZ", "AAA", "LOL", "US", "12$", ""])
    def test_bogus_codes_rejected(self, bad):
        # The whole point of the gate: invalid 3-letter strings must not slip through.
        with pytest.raises(ValueError):
            normalize_currency(bad)

    @pytest.mark.parametrize("crypto", ["BTC", "eth", "bitcoin"])
    def test_crypto_rejected_with_pointer(self, crypto):
        with pytest.raises(ValueError, match="cryptocurrency"):
            normalize_currency(crypto)
