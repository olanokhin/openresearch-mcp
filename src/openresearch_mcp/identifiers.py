"""Shared identifier normalization — the cross-domain chaining gate.

The transport layer (``http``) does **not** cover this: identifier shape is a
property of each tool's parameters, orthogonal to how bytes are fetched. Without
one normalizer, ``get_country_indicator`` takes "Germany", ``search_news`` takes
"DE", and the roadmap's "outputs chain into inputs" stays prose instead of code.

So every tool that accepts a country / date / currency normalizes it here, at the
tool boundary, before it hits the source. Contract:

- country  → ISO-3166-1 **alpha-2**, uppercase ("DE")
- date     → ISO-8601 **YYYY-MM-DD**
- currency → ISO-4217, uppercase ("USD")

Country coverage is the full ISO-3166-1 set via ``pycountry`` (alpha-2, alpha-3,
official + common names), with accent-insensitive matching so "Cote d'Ivoire"
resolves like "Côte d'Ivoire". A small ``_COUNTRY_ALIASES`` table adds the human
short-forms ISO names miss ("usa", "uk", "south korea", "uae"). Anything truly
unrecognised raises ``ValueError`` telling the caller to pass an ISO code.
"""

from __future__ import annotations

import unicodedata
from datetime import date, datetime

import pycountry

# Human aliases that ISO names do not cover cleanly, or where user intent is
# stronger than a strict official name lookup.
_COUNTRY_ALIASES = {
    "america": "US",
    "britain": "GB",
    "czech republic": "CZ",
    "hong kong": "HK",
    "iran": "IR",
    "korea": "KR",
    "laos": "LA",
    "moldova": "MD",
    "north korea": "KP",
    "palestine": "PS",
    "russia": "RU",
    "south korea": "KR",
    "syria": "SY",
    "taiwan": "TW",
    "tanzania": "TZ",
    "turkey": "TR",
    "u.k.": "GB",
    "u.s.": "US",
    "u.s.a.": "US",
    "uae": "AE",
    "uk": "GB",
    "usa": "US",
    "vatican": "VA",
    "venezuela": "VE",
    "vietnam": "VN",
}


def _fold(value: str) -> str:
    """Casefold + strip accents, so "Côte d'Ivoire" and "cote d'ivoire" key alike."""
    normalized = unicodedata.normalize("NFKD", value.strip().casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _build_country_maps() -> tuple[dict[str, str], dict[str, str], set[str]]:
    name_to_alpha2 = {_fold(name): code for name, code in _COUNTRY_ALIASES.items()}
    alpha3_to_alpha2 = {}
    valid_alpha2 = set()

    for country in pycountry.countries:
        alpha2 = country.alpha_2
        valid_alpha2.add(alpha2)
        alpha3_to_alpha2[country.alpha_3] = alpha2
        name_to_alpha2[_fold(country.name)] = alpha2
        if hasattr(country, "official_name"):
            name_to_alpha2[_fold(country.official_name)] = alpha2
        if hasattr(country, "common_name"):
            name_to_alpha2[_fold(country.common_name)] = alpha2

    return name_to_alpha2, alpha3_to_alpha2, valid_alpha2


_NAME_TO_ALPHA2, _ALPHA3_TO_ALPHA2, _VALID_ALPHA2 = _build_country_maps()


def normalize_country(value: str) -> str:
    """Return an ISO-3166-1 alpha-2 code (uppercase) for a country name or code.

    Accepts alpha-2 ("de"), alpha-3 ("deu"), or a common English name ("Germany").

    Raises:
        ValueError: empty input, or a value outside the recognised set. The message
            tells the caller to pass an ISO code — callers surface this to the agent.
    """
    if not value or not value.strip():
        raise ValueError("country is empty")
    key = value.strip()
    upper = key.upper()
    if len(upper) == 2 and upper in _VALID_ALPHA2:
        return upper
    if len(upper) == 3 and upper in _ALPHA3_TO_ALPHA2:
        return _ALPHA3_TO_ALPHA2[upper]
    normalized = _fold(key)
    if normalized in _NAME_TO_ALPHA2:
        return _NAME_TO_ALPHA2[normalized]
    raise ValueError(
        f"unrecognised country {value!r}; pass an ISO-3166 alpha-2 code (e.g. 'DE')"
    )


_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%d/%m/%Y")
_DATE_FORMATS_HELP = "YYYY-MM-DD (also YYYY/MM/DD, DD.MM.YYYY, DD/MM/YYYY, or a date/datetime object)"


def normalize_date(value: str | date | datetime) -> str:
    """Return a date as ISO-8601 ``YYYY-MM-DD``.

    Accepts a ``date``/``datetime`` object (so internal callers can pass objects
    directly) or a string in ISO ``YYYY-MM-DD`` plus the common ``YYYY/MM/DD`` /
    ``DD.MM.YYYY`` / ``DD/MM/YYYY`` typings.

    Raises:
        ValueError: unparseable or non-existent date (e.g. 2026-13-40).
    """
    if isinstance(value, datetime):  # check before date — datetime subclasses date
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not value or not value.strip():
        raise ValueError("date is empty")
    text = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date {value!r}; use ISO-8601 {_DATE_FORMATS_HELP}")


def normalize_date_range(
    start: str | date | datetime, end: str | date | datetime
) -> tuple[str, str]:
    """Normalize a ``(start, end)`` pair to ISO strings, asserting ``start <= end``.

    Catches inverted ranges at the tool boundary rather than letting a source return
    empty/odd results. ISO ``YYYY-MM-DD`` strings sort chronologically, so the
    comparison is a plain string compare.

    Raises:
        ValueError: either date is invalid, or ``start`` is after ``end``.
    """
    start_iso = normalize_date(start)
    end_iso = normalize_date(end)
    if start_iso > end_iso:
        raise ValueError(f"date range start {start_iso} is after end {end_iso}")
    return start_iso, end_iso


def normalize_year(value: str | int) -> int:
    """Return a 4-digit year as int (for yearly series like World Bank).

    Raises:
        ValueError: not a plausible 4-digit year (1000–2999).
    """
    try:
        year = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unrecognised year {value!r}") from exc
    if not 1000 <= year <= 2999:
        raise ValueError(f"year out of range: {year}")
    return year


# Human words for currencies that ISO names don't match cleanly. Deliberately
# resolves ambiguous words to the dominant intent ("dollar" → USD, "pound" → GBP);
# pass the explicit ISO code for any other (CAD, EGP, …).
_CURRENCY_ALIASES = {
    "dollar": "USD", "us dollar": "USD", "usd dollar": "USD", "american dollar": "USD",
    "buck": "USD", "bucks": "USD",
    "euro": "EUR", "euros": "EUR",
    "pound": "GBP", "sterling": "GBP", "pound sterling": "GBP",
    "gbp pound": "GBP", "british pound": "GBP", "quid": "GBP",
    "yen": "JPY",
    "yuan": "CNY", "renminbi": "CNY", "rmb": "CNY",
    "ruble": "RUB", "rouble": "RUB",
}


def _build_currency_maps() -> tuple[dict[str, str], set[str]]:
    valid = {c.alpha_3 for c in pycountry.currencies}
    name_to_code = {_fold(c.name): c.alpha_3 for c in pycountry.currencies}
    # Aliases are authoritative — apply last so a deliberate "dollar" → USD is not
    # shadowed by an ISO currency name that happens to fold to the same key.
    name_to_code.update({_fold(word): code for word, code in _CURRENCY_ALIASES.items()})
    return name_to_code, valid


_CURRENCY_NAME_TO_CODE, _VALID_CURRENCY = _build_currency_maps()

# Common crypto symbols, recognised only to give a *clear* rejection rather than a
# confusing "unrecognised ISO-4217" error. Crypto is NOT a fiat currency — it has
# different rules and a source-specific id space (CoinGecko), so it belongs to the
# crypto tool's own normalizer, not here. See roadmap get_crypto_price (0.3.0).
_KNOWN_CRYPTO = {"BTC", "ETH", "USDT", "USDC", "BNB", "XRP", "SOL", "ADA", "DOGE", "BITCOIN", "ETHEREUM"}


def normalize_currency(value: str) -> str:
    """Return a real ISO-4217 fiat currency code (uppercase), e.g. "usd" → "USD".

    Validates against the full ISO-4217 set (via pycountry), so bogus 3-letter
    strings like "ZZZ" are rejected at the boundary instead of failing downstream.
    Accepts the code itself or a common word ("euro", "pound", "yen").

    Crypto symbols (BTC, ETH, bitcoin) are intentionally rejected with a pointer —
    they are not ISO-4217 and have a separate, source-specific id space.

    Raises:
        ValueError: empty, a crypto symbol, or not a recognised ISO-4217 currency.
    """
    if not value or not value.strip():
        raise ValueError("currency is empty")
    text = value.strip()
    upper = text.upper()
    if len(upper) == 3 and upper in _VALID_CURRENCY:
        return upper
    if upper in _KNOWN_CRYPTO:
        raise ValueError(
            f"{value!r} is a cryptocurrency, not an ISO-4217 fiat currency; "
            "use the crypto tool for coin prices"
        )
    folded = _fold(text)
    if folded in _CURRENCY_NAME_TO_CODE:
        return _CURRENCY_NAME_TO_CODE[folded]
    raise ValueError(f"unrecognised currency {value!r}; use an ISO-4217 code (e.g. 'USD')")


def today_iso() -> str:
    """Today's date as ISO-8601 ``YYYY-MM-DD`` (UTC-naive). Convenience for default ranges."""
    return date.today().isoformat()
