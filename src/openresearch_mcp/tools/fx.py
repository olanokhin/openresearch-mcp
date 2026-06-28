"""Foreign-exchange rates via Frankfurter (ECB reference rates) — zero-auth, no key.

Three shapes off one host (`api.frankfurter.dev`): latest, a single historical date,
and a date-range series. The ECB publishes ~30 major currencies on business days
(no weekends/holidays), so Frankfurter snaps a requested date to the last available
business day. ``group`` downsampling is done client-side — the API has no native
grouping, and a multi-year daily series is otherwise hundreds of rows.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from openresearch_mcp.constants import MAX_TEXT_CHARS
from openresearch_mcp.formatting import format_untrusted
from openresearch_mcp.http import fetch_json, tool_safe
from openresearch_mcp.identifiers import normalize_currency, normalize_date, normalize_date_range

_FRANKFURTER = "https://api.frankfurter.dev/v1"


def _rates_line(rates: dict[str, Any]) -> str:
    return ", ".join(f"{sym} {rate}" for sym, rate in rates.items())


def _downsample(series: dict[str, dict], group: str) -> dict[str, dict]:
    """Keep the last observation per week/month bucket (end-of-period rate).

    ``series`` maps date → {sym: rate}. Iterating in date order and overwriting the
    bucket leaves the latest date in each period. Bad date strings are skipped, not
    crashed (defensive parse of an external body).
    """
    last_day: dict[str, str] = {}  # bucket key -> latest date seen in it
    for day in sorted(series):
        try:
            d = date.fromisoformat(day)
        except (TypeError, ValueError):
            continue
        key = day[:7] if group == "month" else f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
        last_day[key] = day  # iterating in order → final write is the latest date
    return {day: series[day] for day in last_day.values()}


@tool_safe
def get_fx_rate(
    symbols: str = "",
    base: str = "USD",
    start: str | None = None,
    end: str | None = None,
    group: str | None = None,
) -> str:
    """Currency exchange rates (ECB via Frankfurter): latest, historical, or a series.

    Args:
        symbols: Target currency code(s), comma-separated (e.g. "EUR,GBP,JPY"). Empty
            → all available currencies.
        base: Base currency to quote against (default "USD").
        start: Range/point start date (ISO ``YYYY-MM-DD``). end: Range end date.
            Omit both → latest. One only → that single historical date. Both → series.
        group: Downsample a series to ``"week"`` or ``"month"`` (end-of-period rate).
    """
    try:
        base_code = normalize_currency(base)
    except ValueError as exc:
        return f"Invalid base currency: {exc}"

    sym_param = ""
    if symbols and symbols.strip():
        try:
            codes = [normalize_currency(s) for s in symbols.split(",") if s.strip()]
        except ValueError as exc:
            return f"Invalid symbol currency: {exc}"
        sym_param = ",".join(codes)

    grp = None
    if group:
        grp = group.strip().lower()
        if grp not in ("week", "month"):
            return f"Unknown group {group!r}; use 'week' or 'month'."

    try:
        if start and end:
            s_iso, e_iso = normalize_date_range(start, end)
            path, mode = f"{s_iso}..{e_iso}", "series"
        elif start or end:
            path, mode = normalize_date(start or end), "point"  # type: ignore[arg-type]
        else:
            path, mode = "latest", "point"
    except ValueError as exc:
        return f"Invalid date: {exc}"

    params: dict[str, Any] = {"base": base_code}
    if sym_param:
        params["symbols"] = sym_param
    data = fetch_json(f"{_FRANKFURTER}/{path}", source="Frankfurter (ECB)", params=params, timeout=15)

    rates = data.get("rates") if isinstance(data, dict) else None
    if not rates:
        return f"No FX data for base {base_code} over that period."

    if mode == "point":
        header = f"{base_code} → {sym_param or 'all'} (as of {data.get('date', 'latest')}):"
        body = f"{header}\n  {_rates_line(rates)}"
    else:
        if grp:
            rates = _downsample(rates, grp)
        header = (
            f"{base_code} → {sym_param or 'all'}, "
            f"{data.get('start_date', '?')}..{data.get('end_date', '?')} "
            f"({len(rates)} points{', ' + grp if grp else ''}):"
        )
        lines = [header] + [f"  {day}: {_rates_line(r)}" for day, r in sorted(rates.items())]
        body = "\n".join(lines)

    return format_untrusted("FX rates", body[:MAX_TEXT_CHARS])
