"""Tests for the zero-auth Bluesky tools (search users, profile, feed)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from openresearch_mcp.tools.bluesky import (
    _count,
    _fmt_dt,
    _handle,
    get_bluesky_profile,
    read_bluesky_feed,
    search_bluesky_users,
)

PATCH = "openresearch_mcp.http.requests.get"


def _ok(data: dict) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = data
    r.raise_for_status.return_value = None
    return r


def _post(text: str, *, reply: bool = False, likes: int = 10, reposts: int = 2,
          created: str = "2026-06-26T20:36:12.809Z", repost: bool = False) -> dict:
    rec: dict = {"text": text, "createdAt": created}
    if reply:
        rec["reply"] = {"parent": {"uri": "x"}}
    item: dict = {"post": {"record": rec, "likeCount": likes, "repostCount": reposts}}
    if repost:
        item["reason"] = {"$type": "app.bsky.feed.defs#reasonRepost"}
    return item


class TestHelpers:
    def test_handle_strips_at(self):
        assert _handle("@user.bsky.social") == "user.bsky.social"
        assert _handle("  user.bsky.social ") == "user.bsky.social"

    def test_count_thousands(self):
        assert _count(33888169) == "33,888,169"
        assert _count(None) == "?"

    def test_fmt_dt(self):
        assert _fmt_dt("2026-06-26T20:36:12.809Z") == "2026-06-26 20:36"
        assert _fmt_dt("weird") == "weird"


class TestSearchUsers:
    def test_success(self):
        data = {"actors": [{"handle": "jane.bsky.social", "displayName": "Jane", "description": "neuro researcher"}]}
        with patch(PATCH, return_value=_ok(data)):
            result = search_bluesky_users("neuro")
        assert "Jane (@jane.bsky.social)" in result
        assert "neuro researcher" in result
        assert result.startswith("[untrusted Bluesky users")

    def test_empty_query(self):
        assert "Provide a name" in search_bluesky_users("  ")

    def test_no_results(self):
        with patch(PATCH, return_value=_ok({"actors": []})):
            assert "No Bluesky users found" in search_bluesky_users("zzzqwerty")

    def test_non_dict_actor_skipped(self):
        data = {"actors": [{"handle": "a.bsky.social", "displayName": "A"}, "not-a-dict"]}
        with patch(PATCH, return_value=_ok(data)):
            result = search_bluesky_users("x")
        assert "Found 1 Bluesky users" in result

    def test_actor_without_handle_skipped(self):
        # No handle = not actionable; must be dropped, not rendered as "@None".
        data = {"actors": [{"displayName": "No Handle"}, {"handle": "real.bsky.social", "displayName": "Real"}]}
        with patch(PATCH, return_value=_ok(data)):
            result = search_bluesky_users("x")
        assert "@None" not in result
        assert "Found 1 Bluesky users" in result
        assert "Real (@real.bsky.social)" in result

    def test_max_results_clamped(self):
        with patch(PATCH, return_value=_ok({"actors": []})) as g:
            search_bluesky_users("x", max_results=999)
        assert g.call_args[1]["params"]["limit"] == 25

    def test_non_numeric_max_results(self):
        with patch(PATCH, side_effect=AssertionError("no network")):
            assert "Invalid max_results" in search_bluesky_users("x", max_results="abc")  # type: ignore[arg-type]

    def test_transport_graceful(self):
        with patch(PATCH, side_effect=requests.ConnectionError("boom")):
            assert "Could not reach" in search_bluesky_users("x")


class TestGetProfile:
    def _profile(self) -> dict:
        return {
            "handle": "bsky.app", "displayName": "Bluesky", "description": "official account",
            "followersCount": 33888169, "followsCount": 8, "postsCount": 795,
        }

    def test_success_with_formatted_counts(self):
        with patch(PATCH, return_value=_ok(self._profile())):
            result = get_bluesky_profile("@bsky.app")
        assert "Bluesky (@bsky.app)" in result
        assert "Followers: 33,888,169 · Following: 8 · Posts: 795" in result
        assert "official account" in result
        assert result.startswith("[untrusted Bluesky profile")

    def test_handle_at_stripped_in_request(self):
        with patch(PATCH, return_value=_ok(self._profile())) as g:
            get_bluesky_profile("@bsky.app")
        assert g.call_args[1]["params"]["actor"] == "bsky.app"

    def test_empty_handle(self):
        assert "Provide a Bluesky handle" in get_bluesky_profile("  ")

    def test_not_found(self):
        with patch(PATCH, return_value=_ok({})):  # no "handle" field
            assert "No Bluesky profile found" in get_bluesky_profile("ghost.bsky.social")

    def test_transport_graceful(self):
        with patch(PATCH, side_effect=requests.ConnectionError("boom")):
            assert "Could not reach" in get_bluesky_profile("x.bsky.social")


class TestReadFeed:
    def test_filters_reposts_and_replies(self):
        feed = {"feed": [
            _post("a repost", repost=True),
            _post("a reply", reply=True),
            _post("original thoughts on neuroscience"),
        ]}
        with patch(PATCH, return_value=_ok(feed)):
            result = read_bluesky_feed("jane.bsky.social")
        assert "original thoughts on neuroscience" in result
        assert "a repost" not in result
        assert "a reply" not in result

    def test_renders_date_and_counts(self):
        with patch(PATCH, return_value=_ok({"feed": [_post("hello world", likes=101, reposts=4)]})):
            result = read_bluesky_feed("jane.bsky.social")
        assert "[2026-06-26 20:36] hello world" in result
        assert "♥ 101 · ↻ 4" in result

    def test_request_params(self):
        with patch(PATCH, return_value=_ok({"feed": []})) as g:
            read_bluesky_feed("@jane.bsky.social", limit=5)
        params = g.call_args[1]["params"]
        assert params["actor"] == "jane.bsky.social"
        assert params["filter"] == "posts_no_replies"
        assert params["limit"] == 15  # n*3

    def test_only_reposts_replies_gives_message(self):
        feed = {"feed": [_post("r", repost=True), _post("reply", reply=True)]}
        with patch(PATCH, return_value=_ok(feed)):
            assert "No recent original posts" in read_bluesky_feed("jane.bsky.social")

    def test_empty_text_skipped(self):
        feed = {"feed": [_post(""), _post("real post")]}
        with patch(PATCH, return_value=_ok(feed)):
            result = read_bluesky_feed("jane.bsky.social")
        assert "real post" in result

    def test_non_numeric_limit(self):
        with patch(PATCH, side_effect=AssertionError("no network")):
            assert "Invalid limit" in read_bluesky_feed("x.bsky.social", limit="abc")  # type: ignore[arg-type]

    def test_wrapped_untrusted(self):
        with patch(PATCH, return_value=_ok({"feed": [_post("hi")]})):
            assert read_bluesky_feed("x.bsky.social").startswith("[untrusted Bluesky feed")

    def test_transport_graceful(self):
        with patch(PATCH, side_effect=requests.ConnectionError("boom")):
            assert "Could not reach" in read_bluesky_feed("x.bsky.social")


@pytest.mark.integration
def test_live_bluesky_chain():
    # Find a profile, then read its feed — the zero-auth social chain.
    users = search_bluesky_users("neuroscience", max_results=3)
    assert users.startswith("[untrusted Bluesky users")
    profile = get_bluesky_profile("bsky.app")
    assert "Bluesky (@bsky.app)" in profile
    feed = read_bluesky_feed("bsky.app", limit=3)
    assert isinstance(feed, str) and feed
