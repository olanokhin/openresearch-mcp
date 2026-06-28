"""Core utility tools — zero-auth, no external calls, server-generated output."""

from __future__ import annotations

from datetime import UTC, datetime


def get_current_date() -> str:
    """Return the current date and UTC time, so relative requests can be anchored.

    Use this whenever a request is time-relative ("last 30 days", "since last year",
    "recent", "this week") and you need to know what "now" is — do **not** guess the
    date from memory. The UTC date is the anchor for every date-range tool.

    Returns server-generated trusted data (the host's own clock), so unlike the
    fetch tools its output is not wrapped as untrusted content.
    """
    now = datetime.now(UTC)
    return (
        f"Current date (UTC): {now.date().isoformat()}\n"
        f"Current datetime (UTC): {now.isoformat(timespec='seconds')}\n"
        f"Weekday: {now.strftime('%A')}"
    )
