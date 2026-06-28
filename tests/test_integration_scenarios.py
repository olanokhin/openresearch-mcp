"""Cross-domain LIVE integration scenarios.

These hit real APIs (marked integration → excluded from the gating CI job) and
verify the things unit tests can't: that tools actually *chain*, that one
identifier is accepted across domains, and that real-world data edge cases
(null recent year) are handled. Run with: pytest -m integration.
"""
from __future__ import annotations

import re

import pytest

from openresearch_mcp.tools.fx import get_fx_rate
from openresearch_mcp.tools.weather import get_historical_weather
from openresearch_mcp.tools.worldbank import get_country_indicator, search_indicators

pytestmark = pytest.mark.integration

# World Bank indicator code shape, e.g. NY.GDP.PCAP.CD / SP.DYN.LE00.IN
_WB_CODE = re.compile(r"\b([A-Z]{2,3}(?:\.[A-Z0-9]+)+)\b")


def test_search_to_indicator_contract():
    """A code returned by search_indicators must be accepted by get_country_indicator.

    This is the identifier contract end-to-end: search → fetch with no translation.
    """
    found = search_indicators("GDP per capita")
    match = _WB_CODE.search(found)
    assert match, f"no indicator code parsed from:\n{found}"
    code = match.group(1)

    series = get_country_indicator("France", code, start=2018, end=2021)
    assert "France" in series
    assert "2018:" in series or "2019:" in series  # at least one year rendered
    assert not series.lower().startswith("world bank error")


def test_one_country_identifier_across_domains():
    """Japan as name / alpha-2 / alpha-3 all resolve, and chain into FX + weather."""
    by_name = get_country_indicator("Japan", "SP.POP.TOTL", start=2019, end=2021)
    by_a2 = get_country_indicator("JP", "SP.POP.TOTL", start=2019, end=2021)
    by_a3 = get_country_indicator("JPN", "SP.POP.TOTL", start=2019, end=2021)
    assert "Japan" in by_name and "Japan" in by_a2 and "Japan" in by_a3

    # currency word → ISO-4217 (normalize_currency) accepted by FX
    fx = get_fx_rate("yen", base="usd")
    assert "USD → JPY" in fx

    # geocode resolves the capital for the same country in the weather domain
    climate = get_historical_weather("Tokyo", "2021-01-01", "2022-12-31", aggregate="yearly")
    assert "Tokyo, Japan" in climate


def test_recent_year_nulls_filtered():
    """World Bank often has a null latest year; output must not contain None/null."""
    out = get_country_indicator("United States", "SP.POP.TOTL", start=2018, end=2025)
    assert "None" not in out
    assert "null" not in out.lower()
    assert "2018:" in out  # an older, populated year is present
