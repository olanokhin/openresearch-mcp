"""SSRF-safe HTTP fetching: scheme/host validation + bounded streaming download.

Used by tools that fetch arbitrary user/model-supplied URLs (read_url, read_pdf).
Tools that only ever hit fixed, trusted API hosts (GitHub, OpenAlex, HN, SO) do not
need this — their host is not attacker-controlled.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

ALLOWED_SCHEMES = {"http", "https"}
MAX_REDIRECTS = 5
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024  # 25 MiB — generous for academic PDFs
_CHUNK = 64 * 1024


class UnsafeURLError(ValueError):
    """Raised when a URL uses a disallowed scheme or resolves to a private/reserved address."""


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Reject anything that isn't a normal public unicast address."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _peer_ip(resp: requests.Response) -> str | None:
    """Best-effort read of the actual connected peer IP from a streamed response.

    Used to close the DNS-rebinding window: the host may resolve to a public IP
    during _validate_url and a private one at connect time. Checking the real
    socket peer after connect catches that. Returns None if the socket cannot be
    introspected; callers must fail closed in that case.
    """
    try:
        conn = getattr(resp.raw, "_connection", None) or getattr(resp.raw, "connection", None)
        sock = getattr(conn, "sock", None)
        if sock is None:
            return None
        return sock.getpeername()[0].split("%")[0]
    except Exception:
        return None


def _validate_url(url: str) -> None:
    """Validate scheme and that EVERY resolved IP is public.

    Resolving all A/AAAA records and rejecting if any is internal defeats
    round-robin DNS that mixes a public and a private record. The residual
    DNS-rebinding window is closed after connect by _peer_ip().
    """
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"only http/https URLs are allowed (got {parsed.scheme or 'none'!r})")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL has no host")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"could not resolve host {host!r}") from exc

    for info in infos:
        raw_ip = info[4][0].split("%")[0]  # strip IPv6 zone id, e.g. fe80::1%eth0
        ip = ipaddress.ip_address(raw_ip)
        if _ip_is_blocked(ip):
            raise UnsafeURLError(f"host resolves to a blocked address ({ip})")


def safe_get(
    url: str,
    *,
    timeout: float,
    headers: dict[str, str] | None = None,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> requests.Response:
    """Fetch a URL with SSRF protection and a hard download cap.

    Validates scheme + resolved IPs, follows redirects manually (re-validating
    each hop instead of trusting requests' redirect handling), and streams the
    body, aborting once it exceeds ``max_bytes``. The returned response has its
    body already read, so ``.content`` / ``.text`` work normally.

    Raises:
        UnsafeURLError: blocked scheme/address, too many redirects, or oversized body.
        requests.RequestException: underlying network/HTTP failures.
    """
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        _validate_url(current)
        resp = requests.get(
            current, timeout=timeout, headers=headers, stream=True, allow_redirects=False
        )

        # Close the DNS-rebinding window: verify the IP we actually connected to.
        peer = _peer_ip(resp)
        if peer is None:
            resp.close()
            raise UnsafeURLError("could not verify connected peer address")
        if _ip_is_blocked(ipaddress.ip_address(peer)):
            resp.close()
            raise UnsafeURLError(f"connection resolved to a blocked address ({peer})")

        if resp.is_redirect or resp.is_permanent_redirect:
            location = resp.headers.get("Location")
            resp.close()
            if not location:
                raise UnsafeURLError("redirect response without a Location header")
            current = urljoin(current, location)
            continue

        content_length = resp.headers.get("Content-Length")
        if content_length and content_length.isdigit() and int(content_length) > max_bytes:
            resp.close()
            raise UnsafeURLError(f"response too large ({content_length} bytes > {max_bytes})")

        body = bytearray()
        try:
            for chunk in resp.iter_content(_CHUNK):
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise UnsafeURLError(f"response exceeded {max_bytes} bytes")
        finally:
            resp.close()

        # Make .content / .text return the bytes we streamed.
        resp._content = bytes(body)
        resp._content_consumed = True
        return resp

    raise UnsafeURLError(f"too many redirects (>{MAX_REDIRECTS})")
