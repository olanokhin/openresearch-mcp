"""SSRF regression tests for safefetch — internal-address rejection, redirect
re-validation, scheme allowlist, and download byte cap. These guard against
silent regressions in the SSRF protection (OWASP LLM06 / PIPE01 / PIPE12)."""
from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from openresearch_mcp.safefetch import UnsafeURLError, _validate_url, safe_get


def _addrinfo(*ips: str) -> list:
    """Build a socket.getaddrinfo-style result for the given IPs."""
    out = []
    for ip in ips:
        if ":" in ip:
            out.append((socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 0, 0, 0)))
        else:
            out.append((socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 0)))
    return out


def _resolver(mapping: dict[str, list[str]]):
    def _inner(host, port, *args, **kwargs):
        if host not in mapping:
            raise socket.gaierror(f"no mapping for {host}")
        return _addrinfo(*mapping[host])
    return _inner


class FakeResp:
    def __init__(self, *, status=200, headers=None, chunks=(b"",), is_redirect=False):
        self.status_code = status
        self.headers = headers or {}
        self.is_redirect = is_redirect
        self.is_permanent_redirect = False
        self._chunks = chunks
        self.closed = False
        self._content = None
        self._content_consumed = False
        sock = type("S", (), {"getpeername": lambda self: ("93.184.216.34", 443)})()
        self.raw = type("R", (), {"_connection": type("C", (), {"sock": sock})()})()

    def iter_content(self, _n):
        yield from self._chunks

    def close(self):
        self.closed = True

    @property
    def content(self):
        return self._content


class TestValidateUrl:
    def test_rejects_non_http_scheme(self):
        with pytest.raises(UnsafeURLError):
            _validate_url("ftp://example.com/x")

    def test_rejects_file_scheme(self):
        with pytest.raises(UnsafeURLError):
            _validate_url("file:///etc/passwd")

    def test_rejects_missing_host(self):
        with pytest.raises(UnsafeURLError):
            _validate_url("http://")

    @pytest.mark.parametrize("ip", [
        "127.0.0.1",          # loopback
        "169.254.169.254",    # cloud metadata / link-local
        "10.0.0.5",           # RFC1918 private
        "192.168.1.1",        # RFC1918 private
        "172.16.0.1",         # RFC1918 private
        "0.0.0.0",            # unspecified
        "::1",                # IPv6 loopback
        "fe80::1",            # IPv6 link-local
        "::ffff:10.0.0.5",    # IPv4-mapped private
        "64:ff9b::a00:5",     # NAT64 for 10.0.0.5
    ])
    def test_rejects_internal_addresses(self, ip):
        with patch("openresearch_mcp.safefetch.socket.getaddrinfo", _resolver({"evil.test": [ip]})):
            with pytest.raises(UnsafeURLError):
                _validate_url("http://evil.test/")

    def test_allows_public_address(self):
        with patch("openresearch_mcp.safefetch.socket.getaddrinfo", _resolver({"example.com": ["93.184.216.34"]})):
            _validate_url("https://example.com/page")  # no raise

    def test_rejects_round_robin_with_one_private(self):
        # A public + a private record: must reject (defeats DNS round-robin SSRF).
        with patch("openresearch_mcp.safefetch.socket.getaddrinfo",
                   _resolver({"mixed.test": ["93.184.216.34", "10.0.0.5"]})):
            with pytest.raises(UnsafeURLError):
                _validate_url("http://mixed.test/")

    def test_unresolvable_host_raises(self):
        with patch("openresearch_mcp.safefetch.socket.getaddrinfo", _resolver({})):
            with pytest.raises(UnsafeURLError):
                _validate_url("http://nonexistent.test/")


class TestSafeGet:
    def test_successful_fetch_returns_body(self):
        with patch("openresearch_mcp.safefetch.socket.getaddrinfo", _resolver({"example.com": ["93.184.216.34"]})), \
             patch("openresearch_mcp.safefetch.requests.get", return_value=FakeResp(chunks=[b"hello ", b"world"])):
            resp = safe_get("https://example.com/x", timeout=5)
        assert resp.content == b"hello world"

    @pytest.mark.integration
    def test_real_public_fetch_exposes_peer_ip(self):
        resp = safe_get("https://example.com/", timeout=10, max_bytes=256 * 1024)
        assert b"Example Domain" in resp.content

    def test_rejects_oversized_content_length(self):
        big = FakeResp(headers={"Content-Length": "999999999"}, chunks=[b"x"])
        with patch("openresearch_mcp.safefetch.socket.getaddrinfo", _resolver({"example.com": ["93.184.216.34"]})), \
             patch("openresearch_mcp.safefetch.requests.get", return_value=big):
            with pytest.raises(UnsafeURLError):
                safe_get("https://example.com/x", timeout=5, max_bytes=1024)
        assert big.closed

    def test_aborts_when_stream_exceeds_cap(self):
        # No Content-Length header, but the streamed body blows the budget.
        flood = FakeResp(chunks=[b"x" * 100, b"x" * 100])
        with patch("openresearch_mcp.safefetch.socket.getaddrinfo", _resolver({"example.com": ["93.184.216.34"]})), \
             patch("openresearch_mcp.safefetch.requests.get", return_value=flood):
            with pytest.raises(UnsafeURLError):
                safe_get("https://example.com/x", timeout=5, max_bytes=50)
        assert flood.closed

    def test_redirect_to_internal_is_blocked(self):
        # Public origin 302s to the metadata endpoint — must be re-validated and rejected.
        redirect = FakeResp(status=302, headers={"Location": "http://169.254.169.254/"}, is_redirect=True)
        resolver = _resolver({"example.com": ["93.184.216.34"], "169.254.169.254": ["169.254.169.254"]})
        with patch("openresearch_mcp.safefetch.socket.getaddrinfo", resolver), \
             patch("openresearch_mcp.safefetch.requests.get", return_value=redirect):
            with pytest.raises(UnsafeURLError):
                safe_get("https://example.com/x", timeout=5)
        assert redirect.closed

    def test_rebinding_blocked_by_peer_check(self):
        # Host validates as public, but the actual socket connects to an internal IP
        # (DNS rebinding). The post-connect peer check must reject it.
        resp = FakeResp(chunks=[b"secret"])
        sock = type("S", (), {"getpeername": lambda self: ("169.254.169.254", 443)})()
        resp.raw = type("R", (), {"_connection": type("C", (), {"sock": sock})()})()
        with patch("openresearch_mcp.safefetch.socket.getaddrinfo", _resolver({"example.com": ["93.184.216.34"]})), \
             patch("openresearch_mcp.safefetch.requests.get", return_value=resp):
            with pytest.raises(UnsafeURLError):
                safe_get("https://example.com/x", timeout=5)
        assert resp.closed

    def test_missing_peer_ip_fails_closed(self):
        resp = FakeResp(chunks=[b"secret"])
        resp.raw = type("R", (), {"_connection": None})()
        with patch("openresearch_mcp.safefetch.socket.getaddrinfo", _resolver({"example.com": ["93.184.216.34"]})), \
             patch("openresearch_mcp.safefetch.requests.get", return_value=resp):
            with pytest.raises(UnsafeURLError, match="could not verify connected peer address"):
                safe_get("https://example.com/x", timeout=5)
        assert resp.closed

    def test_too_many_redirects(self):
        def always_redirect(*args, **kwargs):
            return FakeResp(status=302, headers={"Location": "https://example.com/next"}, is_redirect=True)
        with patch("openresearch_mcp.safefetch.socket.getaddrinfo", _resolver({"example.com": ["93.184.216.34"]})), \
             patch("openresearch_mcp.safefetch.requests.get", side_effect=always_redirect):
            with pytest.raises(UnsafeURLError):
                safe_get("https://example.com/x", timeout=5)
