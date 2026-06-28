"""Tests for core utility tools."""
from __future__ import annotations

import re
from datetime import UTC, datetime

from openresearch_mcp.tools.core import get_current_date


def test_returns_today_utc_iso_date():
    result = get_current_date()
    today = datetime.now(UTC).date().isoformat()
    assert f"Current date (UTC): {today}" in result


def test_includes_datetime_and_weekday():
    result = get_current_date()
    assert "Current datetime (UTC):" in result
    assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", result)
    assert "Weekday:" in result


def test_not_wrapped_as_untrusted():
    # Server's own clock is trusted output — must NOT carry the untrusted-data notice.
    result = get_current_date()
    assert not result.startswith("[untrusted")
    assert "untrusted" not in result
