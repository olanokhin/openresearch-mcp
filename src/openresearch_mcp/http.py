"""Shared HTTP transport for fixed-host API tools.

Tools that fetch attacker-controlled URLs (read_url, read_pdf) use ``safefetch``
instead — their host is not trusted. This module is for the *other* class: tools
that hit fixed, trusted API hosts (OpenAlex, HN, Stack Overflow, GitHub, World
Bank, GDELT, …). The host is not attacker-controlled there, so SSRF guarding is
unnecessary, but we still want **one** place that owns:

- timeouts (never an unbounded request),
- the trust-boundary error contract (HTTP status is safe to surface; network
  internals go to logs only),
- non-JSON / rate-limit handling (e.g. GDELT returns plain text when throttled),
- server-side rate-limit throttling + a short response cache, so an agent that
  loops cannot breach a source's hard limit. Rate-limit is a server
  responsibility, never a prompt warning.

Each tool then maps the parsed JSON to text — it does not re-implement transport.
"""

from __future__ import annotations

import functools
import hashlib
import logging
import threading
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
_DEFAULT_HEADERS = {"User-Agent": "openresearch-mcp"}
# Hard ceiling on cached entries, so a high-cardinality caller using cache_ttl can't
# grow the dict without bound. Expired entries are swept first; only if still over
# this cap are the soonest-to-expire entries dropped.
_CACHE_MAX = 512

# Per-source throttle + cache state. Module-level, so tests must reset it between
# cases via reset_http_state() — see the autouse fixture in tests/conftest.py.
# MCP tools may run concurrently on a thread pool, so all access to these dicts
# is guarded by _state_lock, and each rate-limited source serializes through its
# own lock in _source_locks (so two concurrent calls can't both slip the gate).
_last_call: dict[str, float] = {}
_cache: dict[str, tuple[float, Any]] = {}  # key -> (expires_at_monotonic, data)
_source_locks: dict[str, threading.Lock] = {}
_state_lock = threading.Lock()


def _source_lock(source: str) -> threading.Lock:
    with _state_lock:
        lock = _source_locks.get(source)
        if lock is None:
            lock = threading.Lock()
            _source_locks[source] = lock
        return lock


def _evict_locked(now: float) -> None:
    """Drop expired entries; if still over ``_CACHE_MAX``, drop the soonest to expire.

    Caller must hold ``_state_lock``. Runs on each cache write — opportunistic, no
    background thread — so the cache stays bounded without separate machinery.
    """
    expired = [k for k, (expires_at, _) in _cache.items() if expires_at <= now]
    for k in expired:
        del _cache[k]
    overflow = len(_cache) - _CACHE_MAX
    if overflow > 0:
        soonest = sorted(_cache.items(), key=lambda kv: kv[1][0])[:overflow]
        for k, _ in soonest:
            del _cache[k]


class SourceError(Exception):
    """A fixed-host API call failed.

    Carries two distinct messages so the trust boundary is preserved at the point
    the error is raised, not patched up later:

    - ``public`` — safe to surface to the agent. The caller supplied the URL/source
      and can act on it (status code, "rate limited, retry"). No internals.
    - ``log`` — server-log detail only (network errors, response snippets). Never
      surfaced, so we don't leak infrastructure shape to the model.
    """

    def __init__(self, source: str, *, public: str, log: str, status_code: int | None = None) -> None:
        super().__init__(public)
        self.source = source
        self.public = public
        self.log = log
        self.status_code = status_code


def reset_http_state() -> None:
    """Clear throttle + cache state. Call between tests to avoid cross-test bleed."""
    with _state_lock:
        _last_call.clear()
        _cache.clear()
        _source_locks.clear()


def _cache_key(url: str, params: dict[str, Any] | None, headers: dict[str, str]) -> str:
    """Cache key over url + params + headers.

    Headers are part of the key on purpose: they carry auth/identity context
    (API keys, OpenAlex polite-pool mailto). Keying on url+params alone would let
    a response fetched under one credential be served to a call made under
    another — a cache-poisoning / credential-mixing bug.

    The header contribution is *hashed*, not stored verbatim: an Authorization
    token must not persist in memory as a plaintext cache-dict key. The digest
    still separates credentials uniquely, so the anti-mixing guarantee holds.
    """
    parts = [url]
    if params:
        parts.append(urlencode(sorted(params.items())))
    header_blob = urlencode(sorted(headers.items()))
    parts.append(hashlib.sha256(header_blob.encode()).hexdigest()[:16])
    return "|".join(parts)


def fetch_json(
    url: str,
    *,
    source: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    min_interval: float = 0.0,
    cache_ttl: float = 0.0,
) -> Any:
    """GET ``url`` and return parsed JSON, or raise :class:`SourceError`.

    One entry point for every fixed-host JSON call, so timeout, error contract and
    non-JSON handling are identical everywhere — rather than re-derived per tool.

    Args:
        source: Human-readable source name, used in messages/logs (e.g. "OpenAlex").
        min_interval: Minimum seconds between live calls to this ``source``. Set for
            rate-limited APIs (GDELT: 5.0); the call blocks the remainder if needed.
        cache_ttl: If > 0, serve a cached JSON body for this URL+params+headers for
            that many seconds. Pairs with ``min_interval`` to absorb an agent that loops.

    Raises:
        SourceError: network failure, non-2xx status, or a non-JSON body.
    """
    request_headers = {**_DEFAULT_HEADERS, **(headers or {})}
    key = _cache_key(url, params, request_headers)

    def _cache_get() -> Any:
        if cache_ttl <= 0:
            return None
        with _state_lock:
            cached = _cache.get(key)
        if cached is not None and time.monotonic() < cached[0]:  # cached[0] = expiry
            return cached[1]
        return None

    hit = _cache_get()
    if hit is not None:
        return hit

    # For a rate-limited source, hold its lock across the throttle gate + request so
    # two concurrent calls can't both read the same stale "last call" and slip past.
    lock = _source_lock(source) if min_interval > 0 else None
    if lock is not None:
        lock.acquire()
    try:
        if lock is not None:
            # Another thread may have filled the cache while we waited for the lock.
            hit = _cache_get()
            if hit is not None:
                return hit
            with _state_lock:
                last = _last_call.get(source)
            if last is not None:
                wait = min_interval - (time.monotonic() - last)
                if wait > 0:
                    time.sleep(wait)

        try:
            resp = requests.get(url, params=params, headers=request_headers, timeout=timeout)
        except requests.RequestException as exc:
            # Network-layer failure: don't surface internals (host shape, DNS, TLS).
            raise SourceError(
                source, public=f"Could not reach {source}. Try again shortly.", log=str(exc)
            ) from exc
        finally:
            if min_interval > 0:
                with _state_lock:
                    _last_call[source] = time.monotonic()

        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            # Status is about the source the caller already named — safe to surface.
            public = (
                f"{source} rate-limited this request — retry shortly."
                if resp.status_code == 429
                else f"{source} returned HTTP {resp.status_code}."
            )
            raise SourceError(source, public=public, log=str(exc), status_code=resp.status_code) from exc

        try:
            data = resp.json()
        except ValueError as exc:
            # Some sources (e.g. GDELT) return plain text instead of JSON when throttled.
            raise SourceError(
                source,
                public=f"{source} returned a non-JSON response (it may be rate-limiting — retry shortly).",
                log=f"non-JSON body: {resp.text[:200]!r}",
            ) from exc

        if cache_ttl > 0:
            now = time.monotonic()
            with _state_lock:
                _cache[key] = (now + cache_ttl, data)
                _evict_locked(now)
        return data
    finally:
        if lock is not None:
            lock.release()


def scrub_log(value: object) -> str:
    """Flatten CR/LF so external/user content can't forge or split a log line (PIPE11)."""
    return str(value).replace("\n", " ").replace("\r", " ")


def tool_safe(func: Callable[..., str]) -> Callable[..., str]:
    """Wrap a tool so a :class:`SourceError` becomes a clean string, not a raised error.

    Centralises the "graceful, never crash" contract the roadmap requires: the tool
    body calls ``fetch_json`` and maps the result; transport failures are caught here
    once, logged with their server-only detail, and returned as the public message.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return func(*args, **kwargs)
        except SourceError as exc:
            # exc.log carries a request URL (with user query terms) / response snippet →
            # scrub newlines before logging so it can't forge audit lines.
            logger.warning("%s failed: %s", exc.source, scrub_log(exc.log))
            return exc.public

    return wrapper
