"""Cryptocurrency prices via CoinGecko (keyless) — zero-auth.

The keyless tier rate-limits aggressively (~30 calls/min, then HTTP 429), so calls
go through the shared transport's throttle + short cache: ``min_interval`` spaces
live calls, ``cache_ttl`` absorbs an agent that re-asks. This is also where crypto
identifiers are normalized (symbol → CoinGecko id) — deliberately source-specific,
not folded into the ISO-4217 ``normalize_currency`` (crypto is not fiat).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote as urlquote

from openresearch_mcp.formatting import format_untrusted
from openresearch_mcp.http import fetch_json, tool_safe

_COINGECKO = "https://api.coingecko.com/api/v3"
# Keyless tier: space live calls and cache briefly so a looping agent can't trip 429.
_MIN_INTERVAL = 1.5
_CACHE_TTL = 30.0

# Common ticker symbols → CoinGecko coin ids. Full names pass through as-is.
_SYMBOL_TO_ID = {
    "btc": "bitcoin", "eth": "ethereum", "usdt": "tether", "bnb": "binancecoin",
    "sol": "solana", "xrp": "ripple", "usdc": "usd-coin", "ada": "cardano",
    "doge": "dogecoin", "trx": "tron", "ton": "the-open-network", "dot": "polkadot",
    "matic": "matic-network", "ltc": "litecoin", "shib": "shiba-inu", "link": "chainlink",
    "avax": "avalanche-2", "bch": "bitcoin-cash", "xlm": "stellar", "atom": "cosmos",
}


def _coin_id(coin: str) -> str:
    key = coin.strip().lower()
    return _SYMBOL_TO_ID.get(key, key)


def _fmt_price(value: Any) -> str:
    """Round a price to 2 decimals — but keep significant digits for sub-cent coins.

    A flat ``round(x, 2)`` would print a $0.00001 token (SHIB etc.) as ``0.00``,
    erasing the value. Below one cent we fall back to significant figures instead.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if v != 0 and abs(v) < 0.01:
        return f"{v:.8f}".rstrip("0").rstrip(".")
    return f"{v:.2f}"


@tool_safe
def get_crypto_price(coin: str, vs: str = "usd", days: int | None = None) -> str:
    """Cryptocurrency price: current, or daily history over a window. No API key.

    Args:
        coin: Coin id or ticker symbol (e.g. "bitcoin", "btc", "ethereum", "eth").
        vs: Quote currency (e.g. "usd", "eur", "btc"). Default "usd".
        days: If given, return daily price history for the last N days (1–365);
            omit for the current price only.
    """
    if not coin or not coin.strip():
        return "Provide a coin id or symbol, e.g. 'bitcoin' or 'btc'."
    coin_id = _coin_id(coin)
    quote = vs.strip().lower() or "usd"

    if days is None:
        data = fetch_json(
            f"{_COINGECKO}/simple/price",
            source="CoinGecko",
            params={"ids": coin_id, "vs_currencies": quote},
            timeout=15,
            min_interval=_MIN_INTERVAL,
            cache_ttl=_CACHE_TTL,
        )
        entry = data.get(coin_id) if isinstance(data, dict) else None
        if not entry or entry.get(quote) is None:
            return f"No price for {coin!r} in {quote.upper()}. Check the coin id (e.g. 'bitcoin') and quote currency."
        return format_untrusted("crypto price", f"{coin_id}: {_fmt_price(entry[quote])} {quote.upper()}")

    try:
        n_days = max(1, min(int(days), 365))
    except (TypeError, ValueError):
        return f"Invalid days {days!r}; provide a whole number of days (1–365)."
    data = fetch_json(
        # coin_id is user-derived → URL-encode the path segment (fixed host, but keep
        # special chars from reaching an unintended endpoint).
        f"{_COINGECKO}/coins/{urlquote(coin_id, safe='')}/market_chart",
        source="CoinGecko",
        params={"vs_currency": quote, "days": n_days},
        timeout=20,
        min_interval=_MIN_INTERVAL,
        cache_ttl=_CACHE_TTL,
    )
    prices = data.get("prices") if isinstance(data, dict) else None
    if not prices:
        return f"No price history for {coin!r} in {quote.upper()}. Check the coin id and quote currency."

    # CoinGecko returns many intraday points; collapse to the last value per UTC day.
    per_day: dict[str, float] = {}
    for point in prices:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        ts, price = point[0], point[1]
        try:
            day = datetime.fromtimestamp(ts / 1000, tz=UTC).date().isoformat()
        except (TypeError, ValueError, OSError):
            continue
        per_day[day] = price  # later point in the day wins

    if not per_day:
        return f"No usable price points for {coin!r}."
    lines = [f"{coin_id} in {quote.upper()}, last {n_days} days (daily):"]
    lines += [f"  {day}: {_fmt_price(price)}" for day, price in sorted(per_day.items())]
    return format_untrusted("crypto price", "\n".join(lines))
