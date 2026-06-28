"""World Bank socio-economic indicators — zero-auth, no API key.

Two tools that chain: search_indicators finds the indicator *code* by keyword,
get_country_indicator pulls the yearly series for a country + that code. The World
Bank v2 API returns a ``[metadata, rows]`` two-element array (not an object) and
answers some errors with HTTP 200 + a ``message`` payload, so both are handled here.
"""

from __future__ import annotations

from typing import Any

from openresearch_mcp.constants import MAX_TEXT_CHARS
from openresearch_mcp.formatting import format_untrusted
from openresearch_mcp.http import fetch_json, tool_safe
from openresearch_mcp.identifiers import normalize_country, normalize_year, today_iso

_WB_BASE = "https://api.worldbank.org/v2"
# WDI (source 2) is the canonical ~1,500-indicator development set. Searching the
# full 29k-indicator catalog per query is impractical; WDI covers what users ask for
# (GDP, population, migration, inflation, life expectancy, …) in a single page.
_WDI_SOURCE = 2
_SEARCH_MAX = 25


def _wb_error(data: Any) -> str | None:
    """Return a World Bank error message if the response is an error payload, else None.

    The API signals some failures with HTTP 200 + ``[{"message": [{"value": ...}]}]``,
    so a non-2xx status (which fetch_json would catch) is not enough on its own.
    """
    if isinstance(data, list) and data and isinstance(data[0], dict) and data[0].get("message"):
        msgs = data[0]["message"]
        if msgs:
            return str(msgs[0].get("value", "unknown error"))
        return "unknown error"
    return None


@tool_safe
def search_indicators(query: str) -> str:
    """Find World Bank indicator codes by keyword, to feed into get_country_indicator.

    Searches the WDI development-indicator set (~1,500 indicators) by name. Returns
    matching ``code — name`` pairs. Use the code (e.g. "NY.GDP.MKTP.CD") with
    get_country_indicator.

    Args:
        query: Keyword(s), e.g. "GDP", "net migration", "life expectancy".
    """
    if not query or not query.strip():
        return "Provide a search keyword, e.g. 'GDP' or 'migration'."

    data = fetch_json(
        f"{_WB_BASE}/indicator",
        source="World Bank",
        params={"format": "json", "source": _WDI_SOURCE, "per_page": 2000},
        timeout=30,
        cache_ttl=3600,  # catalog is near-static; cache so repeated searches don't refetch 1.5 MB
    )
    err = _wb_error(data)
    if err:
        return f"World Bank error: {err}"
    rows = data[1] if isinstance(data, list) and len(data) > 1 else None
    if not rows:
        return "Indicator catalog unavailable; try again shortly."

    tokens = query.lower().split()
    matches = [
        (r["id"], r["name"])
        for r in rows
        if r.get("id") and r.get("name") and all(tok in r["name"].lower() for tok in tokens)
    ]
    if not matches:
        return f"No WDI indicators match {query!r}. Try a broader keyword."

    shown = matches[:_SEARCH_MAX]
    lines = [f"{code} — {name}" for code, name in shown]
    if len(matches) > _SEARCH_MAX:
        lines.append(f"... and {len(matches) - _SEARCH_MAX} more; narrow the keyword.")
    return format_untrusted("World Bank indicators", "\n".join(lines))


def _year_range(start: str | int | None, end: str | int | None) -> str | None:
    """Build the World Bank ``date=`` value from optional start/end years.

    Returns None (omit the param → all available years) when neither is given.
    Raises ValueError on a non-year or an inverted range — the caller surfaces it.
    """
    s = normalize_year(start) if start is not None and start != "" else None
    e = normalize_year(end) if end is not None and end != "" else None
    if s is not None and e is not None:
        if s > e:
            raise ValueError(f"start year {s} is after end year {e}")
        return f"{s}:{e}"
    if s is not None:
        return f"{s}:{today_iso()[:4]}"
    if e is not None:
        return f"1960:{e}"  # WDI series generally begin ~1960
    return None


@tool_safe
def get_country_indicator(
    country: str, indicator: str, start: str | int | None = None, end: str | int | None = None
) -> str:
    """Yearly socio-economic series for a country: GDP, population, inflation, etc.

    Args:
        country: Country name or ISO code (e.g. "Germany", "DE", "DEU").
        indicator: World Bank indicator code (e.g. "NY.GDP.MKTP.CD"). Use
            search_indicators to find a code by keyword.
        start: First year (optional). end: Last year (optional). Omit both for the
            full available range. A single bound extends to the present / back to 1960.
    """
    try:
        iso2 = normalize_country(country)
    except ValueError as exc:
        return f"Invalid country: {exc}"
    code = indicator.strip()
    if not code:
        return "Provide a World Bank indicator code (use search_indicators to find one)."
    try:
        date_range = _year_range(start, end)
    except ValueError as exc:
        return f"Invalid year range: {exc}"

    params: dict[str, Any] = {"format": "json", "per_page": 20000}
    if date_range:
        params["date"] = date_range
    data = fetch_json(
        f"{_WB_BASE}/country/{iso2}/indicator/{code}",
        source="World Bank",
        params=params,
        timeout=20,
    )
    err = _wb_error(data)
    if err:
        return f"World Bank error: {err} (check the indicator code via search_indicators)."
    rows = data[1] if isinstance(data, list) and len(data) > 1 else None
    if not rows:
        return f"No data for {code} in {country!r} for that period."

    # Filter null values (the latest year is often empty) and order oldest→newest.
    # Guard both keys: a malformed row must skip, not KeyError past @tool_safe.
    points = [
        (r["date"], r["value"])
        for r in rows
        if isinstance(r, dict) and r.get("date") and r.get("value") is not None
    ]
    if not points:
        return f"No non-empty values for {code} in {country!r} for that period."
    points.sort(key=lambda p: p[0])

    meta = rows[0]
    indicator_name = (meta.get("indicator") or {}).get("value") or code
    country_name = (meta.get("country") or {}).get("value") or iso2
    lines = [f"{indicator_name} — {country_name}:"]
    lines += [f"  {year}: {value}" for year, value in points]
    return format_untrusted("World Bank", "\n".join(lines)[:MAX_TEXT_CHARS])
