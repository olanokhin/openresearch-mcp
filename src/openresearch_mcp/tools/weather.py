"""Weather tools via Open-Meteo — zero-auth, no API key.

Open-Meteo data is CC BY 4.0, free for non-commercial use (~10k req/day);
commercial use needs their paid plan or self-host. Two fixed hosts are involved:
geocoding (name → lat/lon) and the forecast API.
"""

from __future__ import annotations

from typing import Any

from openresearch_mcp.constants import MAX_TEXT_CHARS
from openresearch_mcp.formatting import format_untrusted
from openresearch_mcp.http import fetch_json, tool_safe
from openresearch_mcp.identifiers import normalize_date_range

# WMO weather interpretation codes → human text, so the agent reads "Clear sky"
# rather than a bare integer. https://open-meteo.com/en/docs (WMO Weather code)
_WMO = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snowfall", 73: "Moderate snowfall", 75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


def _describe_code(code: Any) -> str:
    try:
        return _WMO.get(int(code), f"code {code}")
    except (TypeError, ValueError):
        return f"code {code}"


def _at(seq: list, i: int) -> Any:
    """Index ``seq`` defensively: Open-Meteo *should* return parallel arrays of equal
    length, but a partial/changed response must not crash the tool (@tool_safe only
    catches SourceError, not IndexError). Missing values render as 'N/A'."""
    return seq[i] if i < len(seq) else "N/A"


def _geocode(name: str) -> dict | None:
    """Resolve a place name to its first geocoding match, or None if not found.

    Internal helper (not a standalone tool). Raises SourceError on transport
    failure — the caller is wrapped by @tool_safe, which turns it into a string.
    """
    data = fetch_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        source="Open-Meteo geocoding",
        params={"name": name, "count": 1, "format": "json"},
        timeout=10,
    )
    results = data.get("results") or []
    return results[0] if results else None


@tool_safe
def get_weather_forecast(location: str, days: int = 7) -> str:
    """Current conditions + daily forecast for a place. No API key required.

    Args:
        location: City or place name (e.g. "Berlin", "San Francisco"). Resolved to
            coordinates via Open-Meteo geocoding.
        days: Forecast length in days (1–16, default 7).
    """
    days = max(1, min(days, 16))
    place = _geocode(location)
    if place is None:
        return f"Could not find a location named {location!r}. Try a more specific name."

    data = fetch_json(
        "https://api.open-meteo.com/v1/forecast",
        source="Open-Meteo",
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "timezone": "auto",
            "forecast_days": days,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
        },
        timeout=15,
    )
    # Open-Meteo signals bad params with {"error": true, "reason": ...}.
    if isinstance(data, dict) and data.get("error"):
        return f"Weather service error: {data.get('reason', 'unknown')}"

    label = ", ".join(p for p in (place.get("name"), place.get("country")) if p)
    lines = [f"Weather for {label} ({place['latitude']:.2f}, {place['longitude']:.2f})"]

    current = data.get("current") or {}
    if current:
        lines.append(
            f"Current ({current.get('time', 'now')}): "
            f"{current.get('temperature_2m')}°C, {_describe_code(current.get('weather_code'))}, "
            f"humidity {current.get('relative_humidity_2m')}%, "
            f"wind {current.get('wind_speed_10m')} km/h"
        )

    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    if dates:
        lines.append(f"\nForecast ({len(dates)} days):")
        codes = daily.get("weather_code") or []
        tmax = daily.get("temperature_2m_max") or []
        tmin = daily.get("temperature_2m_min") or []
        precip = daily.get("precipitation_sum") or []
        for i, day in enumerate(dates):
            lines.append(
                f"  {day}: {_at(tmin, i)}–{_at(tmax, i)}°C, {_describe_code(_at(codes, i))}, "
                f"precip {_at(precip, i)} mm"
            )

    return format_untrusted("weather forecast", "\n".join(lines))


def _aggregate(
    dates: list, temps: list, precip: list, width: int
) -> dict[str, dict[str, Any]]:
    """Bucket daily values by date prefix (``width`` 7 = YYYY-MM, 4 = YYYY).

    Climate trend reduction: temperature is averaged within a bucket, precipitation
    summed. Nulls (Open-Meteo's recent ~5-day lag, gaps) are skipped, not counted as
    zero. Insertion order = chronological because the source returns dates in order.
    """
    out: dict[str, dict[str, Any]] = {}
    for i, day in enumerate(dates):
        bucket = out.setdefault(day[:width], {"temps": [], "precip": 0.0})
        t = _at(temps, i)
        if isinstance(t, (int, float)):
            bucket["temps"].append(t)
        p = _at(precip, i)
        if isinstance(p, (int, float)):
            bucket["precip"] += p
    return out


@tool_safe
def get_historical_weather(
    location: str, start: str, end: str, aggregate: str = "monthly"
) -> str:
    """Historical climate series for a place, aggregated for trend analysis. No key.

    Spans ERA5 reanalysis since 1940 (≈5-day lag at the recent end). Daily data is
    *always* aggregated — a multi-year raw daily series is thousands of points.

    Args:
        location: City or place name, resolved via Open-Meteo geocoding.
        start: Range start date (ISO ``YYYY-MM-DD``; common typings also accepted).
        end: Range end date. Must be on or after ``start``.
        aggregate: ``"monthly"`` (mean temp + total precip per month) or ``"yearly"``.
    """
    agg = aggregate.strip().lower()
    if agg in ("month", "monthly"):
        agg, width = "monthly", 7
    elif agg in ("year", "yearly", "annual"):
        agg, width = "yearly", 4
    else:
        return f"Unknown aggregate {aggregate!r}; use 'monthly' or 'yearly'."

    try:
        start_iso, end_iso = normalize_date_range(start, end)
    except ValueError as exc:
        # normalize_* raise ValueError on bad/inverted input; its message is written
        # for the caller, so surface it (@tool_safe only catches SourceError).
        return f"Invalid date range: {exc}"

    place = _geocode(location)
    if place is None:
        return f"Could not find a location named {location!r}. Try a more specific name."

    data = fetch_json(
        "https://archive-api.open-meteo.com/v1/archive",
        source="Open-Meteo archive",
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "start_date": start_iso,
            "end_date": end_iso,
            "timezone": "auto",
            "daily": "temperature_2m_mean,precipitation_sum",
        },
        timeout=30,
    )
    if isinstance(data, dict) and data.get("error"):
        return f"Weather service error: {data.get('reason', 'unknown')}"

    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    if not dates:
        return f"No historical data for {location!r} in {start_iso}..{end_iso}."

    buckets = _aggregate(
        dates, daily.get("temperature_2m_mean") or [], daily.get("precipitation_sum") or [], width
    )

    label = ", ".join(p for p in (place.get("name"), place.get("country")) if p)
    lines = [
        f"Historical weather for {label} ({place['latitude']:.2f}, {place['longitude']:.2f}), "
        f"{start_iso}..{end_iso}, aggregated {agg}:"
    ]
    for key, bucket in buckets.items():
        temps = bucket["temps"]
        temp_str = f"{sum(temps) / len(temps):.1f}°C" if temps else "N/A"
        lines.append(f"  {key}: mean temp {temp_str}, precip {bucket['precip']:.1f} mm")

    return format_untrusted("historical weather", "\n".join(lines)[:MAX_TEXT_CHARS])
