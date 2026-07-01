"""Tests for the shared HTTP transport: fetch_json, SourceError contract, tool_safe."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from openresearch_mcp.http import SourceError, fetch_json, reset_http_state, scrub_log, tool_safe


def _resp(*, json_data=None, status=200, text="", raise_http=False) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.text = text
    if json_data is not None:
        r.json.return_value = json_data
    else:
        r.json.side_effect = ValueError("no json")
    if raise_http:
        r.raise_for_status.side_effect = requests.HTTPError(f"{status} error")
    else:
        r.raise_for_status.return_value = None
    return r


class TestFetchJson:
    def test_returns_parsed_json(self):
        with patch("openresearch_mcp.http.requests.get", return_value=_resp(json_data={"ok": 1})):
            assert fetch_json("https://x.test", source="X") == {"ok": 1}

    def test_passes_params_and_merges_default_user_agent(self):
        with patch("openresearch_mcp.http.requests.get", return_value=_resp(json_data={})) as g:
            fetch_json("https://x.test", source="X", params={"q": "hi"}, headers={"Accept": "json"})
        kwargs = g.call_args[1]
        assert kwargs["params"] == {"q": "hi"}
        assert kwargs["headers"]["User-Agent"] == "openresearch-mcp"
        assert kwargs["headers"]["Accept"] == "json"

    def test_caller_header_overrides_default_user_agent(self):
        with patch("openresearch_mcp.http.requests.get", return_value=_resp(json_data={})) as g:
            fetch_json("https://x.test", source="X", headers={"User-Agent": "custom"})
        assert g.call_args[1]["headers"]["User-Agent"] == "custom"


class TestSourceErrorContract:
    def test_network_error_hides_internals_in_public_message(self):
        boom = requests.ConnectionError("tls handshake to 10.0.0.1 failed")
        with patch("openresearch_mcp.http.requests.get", side_effect=boom):
            with pytest.raises(SourceError) as ei:
                fetch_json("https://x.test", source="OpenAlex")
        # public must NOT leak the underlying network detail; log must keep it.
        assert "10.0.0.1" not in ei.value.public
        assert "OpenAlex" in ei.value.public
        assert "10.0.0.1" in ei.value.log

    def test_http_status_is_surfaced(self):
        with patch("openresearch_mcp.http.requests.get",
                   return_value=_resp(status=503, raise_http=True)):
            with pytest.raises(SourceError) as ei:
                fetch_json("https://x.test", source="SEC")
        assert "503" in ei.value.public
        assert ei.value.status_code == 503

    def test_429_gets_retry_message(self):
        with patch("openresearch_mcp.http.requests.get",
                   return_value=_resp(status=429, raise_http=True)):
            with pytest.raises(SourceError) as ei:
                fetch_json("https://x.test", source="GDELT")
        assert "rate" in ei.value.public.lower()

    def test_non_json_body_becomes_source_error(self):
        # GDELT returns plain text when throttled — must not raise a bare ValueError.
        with patch("openresearch_mcp.http.requests.get",
                   return_value=_resp(json_data=None, text="rate limited, plain text")):
            with pytest.raises(SourceError) as ei:
                fetch_json("https://x.test", source="GDELT")
        assert "non-JSON" in ei.value.public


class TestToolSafe:
    def test_catches_source_error_returns_public(self):
        @tool_safe
        def tool() -> str:
            raise SourceError("X", public="X is down.", log="secret 10.0.0.1 detail")

        result = tool()
        assert result == "X is down."

    def test_passes_through_normal_return(self):
        @tool_safe
        def tool() -> str:
            return "ok"

        assert tool() == "ok"

    def test_does_not_swallow_other_exceptions(self):
        @tool_safe
        def tool() -> str:
            raise KeyError("programming bug")

        with pytest.raises(KeyError):
            tool()

    def test_scrubs_newlines_before_logging(self, caplog):
        # PIPE11: exc.log (URL/response snippet) must not forge or split log lines.
        import logging as _logging

        @tool_safe
        def tool() -> str:
            raise SourceError("X", public="down", log="real line\nFORGED: fake audit entry")

        with caplog.at_level(_logging.WARNING):
            tool()
        assert all("\n" not in r.getMessage() for r in caplog.records)
        assert "FORGED: fake audit entry" in caplog.text  # content kept, just flattened


def test_scrub_log_flattens_cr_lf():
    assert scrub_log("a\nb\r\nc") == "a b  c"


class TestCacheHardening:
    def test_token_not_stored_plaintext_in_cache_key(self):
        import openresearch_mcp.http as http_mod

        reset_http_state()
        secret = "Bearer super-secret-token-xyz"
        with patch("openresearch_mcp.http.requests.get", return_value=_resp(json_data={})):
            fetch_json("https://x.test", source="X", headers={"Authorization": secret}, cache_ttl=60)
        assert http_mod._cache, "expected one cached entry"
        assert all(secret not in k for k in http_mod._cache), "auth token leaked into cache key"

    def test_cache_is_bounded(self):
        import openresearch_mcp.http as http_mod

        reset_http_state()
        n = http_mod._CACHE_MAX + 50
        with patch("openresearch_mcp.http.requests.get", return_value=_resp(json_data={})):
            for i in range(n):
                fetch_json(f"https://x.test/{i}", source="X", cache_ttl=600)
        assert len(http_mod._cache) <= http_mod._CACHE_MAX

    def test_expired_entries_are_swept_on_write(self):
        import openresearch_mcp.http as http_mod

        reset_http_state()

        class _Clock:
            t = 1000.0

            def __call__(self) -> float:
                return self.t

        clock = _Clock()
        with patch("openresearch_mcp.http.requests.get", return_value=_resp(json_data={})), \
             patch("openresearch_mcp.http.time.monotonic", clock):
            fetch_json("https://x.test/a", source="X", cache_ttl=10)  # expires at 1010
            clock.t = 2000.0  # well past expiry
            fetch_json("https://x.test/b", source="X", cache_ttl=10)  # write sweeps 'a'
        keys = list(http_mod._cache)
        assert any("/b" in k for k in keys)
        assert not any("/a" in k for k in keys), "expired entry should have been swept"


class TestThrottleAndCache:
    def test_cache_serves_repeat_within_ttl_without_second_call(self):
        reset_http_state()
        with patch("openresearch_mcp.http.requests.get", return_value=_resp(json_data={"n": 1})) as g:
            a = fetch_json("https://x.test", source="X", cache_ttl=60)
            b = fetch_json("https://x.test", source="X", cache_ttl=60)
        assert a == b == {"n": 1}
        assert g.call_count == 1  # second served from cache

    def test_distinct_params_are_cached_separately(self):
        reset_http_state()
        with patch("openresearch_mcp.http.requests.get", return_value=_resp(json_data={})) as g:
            fetch_json("https://x.test", source="X", params={"q": "a"}, cache_ttl=60)
            fetch_json("https://x.test", source="X", params={"q": "b"}, cache_ttl=60)
        assert g.call_count == 2

    def test_min_interval_sleeps_between_live_calls(self):
        reset_http_state()

        class _Clock:
            t = 0.0

            def __call__(self) -> float:
                return self.t

        clock = _Clock()
        with patch("openresearch_mcp.http.requests.get", return_value=_resp(json_data={})), \
             patch("openresearch_mcp.http.time.sleep") as sleep, \
             patch("openresearch_mcp.http.time.monotonic", clock):
            fetch_json("https://x.test", source="GDELT", min_interval=5.0)  # last call = t0
            clock.t = 1.0  # only 1s elapses before the next call
            fetch_json("https://x.test", source="GDELT", min_interval=5.0)
        # second call was 1.0s after the first → must wait ~4.0s. Robust to how many
        # times monotonic() is read internally (only the clock value matters).
        assert sleep.called
        assert sleep.call_args[0][0] == pytest.approx(4.0, abs=0.01)

    def test_cache_key_separates_credentials(self):
        # A response fetched under one auth header must not be served to a call made
        # under a different one (credential mixing).
        reset_http_state()
        r1 = _resp(json_data={"who": "alice"})
        r2 = _resp(json_data={"who": "bob"})
        with patch("openresearch_mcp.http.requests.get", side_effect=[r1, r2]):
            a = fetch_json("https://x.test", source="X", headers={"Authorization": "alice"}, cache_ttl=60)
            b = fetch_json("https://x.test", source="X", headers={"Authorization": "bob"}, cache_ttl=60)
        assert a == {"who": "alice"}
        assert b == {"who": "bob"}  # not a's cached response

    def test_concurrent_calls_to_same_source_serialize(self):
        # Per-source lock must prevent two rate-limited calls overlapping in flight.
        import threading

        reset_http_state()
        in_flight = {"n": 0}
        overlap = {"seen": False}
        guard = threading.Lock()

        def fake_get(*args, **kwargs):
            with guard:
                in_flight["n"] += 1
                if in_flight["n"] > 1:
                    overlap["seen"] = True
            time.sleep(0.02)  # widen the window where an overlap could be observed
            with guard:
                in_flight["n"] -= 1
            return _resp(json_data={})

        with patch("openresearch_mcp.http.requests.get", side_effect=fake_get), \
             patch("openresearch_mcp.http.time.sleep", lambda *_: None):
            threads = [
                threading.Thread(
                    target=fetch_json, args=("https://x.test",),
                    kwargs={"source": "GDELT", "min_interval": 5.0},
                )
                for _ in range(4)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        assert overlap["seen"] is False
