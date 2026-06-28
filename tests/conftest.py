"""Shared test fixtures."""
from __future__ import annotations

import pytest

from openresearch_mcp.http import reset_http_state


@pytest.fixture(autouse=True)
def _clear_http_state():
    """Reset the module-level throttle + response cache around every test.

    fetch_json keeps per-source state for rate-limit throttling; without this an
    earlier test's cached body or last-call timestamp would bleed into the next
    and make the suite order-dependent.
    """
    reset_http_state()
    yield
    reset_http_state()
