"""Bluesky / AT Protocol public read tools — zero-auth.

Uses the public AppView (``public.api.bsky.app``), which serves public profile and
feed data with no login. These are the zero-auth social tools: find researchers/devs
and read what they've written. Network-wide keyword *post* search is a different,
account-level credential (Bluesky app-password) and is intentionally NOT here — see
the roadmap's `search_bluesky_posts` (🔑 personal-auth, a later wave).
"""

from __future__ import annotations

from typing import Any

from openresearch_mcp.formatting import format_untrusted
from openresearch_mcp.http import fetch_json, tool_safe

_XRPC = "https://public.api.bsky.app/xrpc"


def _handle(actor: str) -> str:
    return actor.strip().lstrip("@")


def _count(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "?"


def _fmt_dt(value: Any) -> str:
    """'2026-06-26T20:36:12.809Z' → '2026-06-26 20:36'. Defensive."""
    s = str(value or "")
    if len(s) >= 16 and s[10] == "T":
        return f"{s[:10]} {s[11:16]}"
    return s


@tool_safe
def search_bluesky_users(query: str, max_results: int = 10) -> str:
    """Find Bluesky profiles by name, handle, or bio text. No API key required.

    Args:
        query: Name, handle, or topic, e.g. "neuroscience" or "Jane Smith".
        max_results: Number of profiles to return (1–25, default 10).
    """
    if not query or not query.strip():
        return "Provide a name, handle, or keyword to search for."
    try:
        n = max(1, min(int(max_results), 25))
    except (TypeError, ValueError):
        return f"Invalid max_results {max_results!r}; provide a whole number (1–25)."

    data = fetch_json(
        f"{_XRPC}/app.bsky.actor.searchActors",
        source="Bluesky",
        params={"q": query.strip(), "limit": n},
        timeout=15,
    )
    actors = data.get("actors") if isinstance(data, dict) else None
    # Require a handle: it's the actionable id (feeds get_bluesky_profile / read_bluesky_feed),
    # and dropping handle-less actors avoids a cosmetic "@None".
    actors = [a for a in actors if isinstance(a, dict) and a.get("handle")] if isinstance(actors, list) else []
    if not actors:
        return f"No Bluesky users found for {query!r}."

    lines = [f'Found {len(actors)} Bluesky users for "{query.strip()}":']
    for a in actors:
        name = a.get("displayName") or a.get("handle") or "Unknown"
        line = f"\n{name} (@{a.get('handle')})"
        bio = str(a.get("description") or "").strip().replace("\n", " ")
        if bio:
            line += f"\n  {bio[:200]}"
        lines.append(line)
    return format_untrusted("Bluesky users", "\n".join(lines))


@tool_safe
def get_bluesky_profile(handle: str) -> str:
    """Full Bluesky profile: bio and follower/following/post counts. No API key.

    Cheap context before reading a feed. Args:
        handle: A Bluesky handle, e.g. "user.bsky.social" (a leading @ is fine).
    """
    if not handle or not handle.strip():
        return "Provide a Bluesky handle, e.g. 'user.bsky.social'."

    data = fetch_json(
        f"{_XRPC}/app.bsky.actor.getProfile",
        source="Bluesky",
        params={"actor": _handle(handle)},
        timeout=15,
    )
    if not isinstance(data, dict) or not data.get("handle"):
        return f"No Bluesky profile found for {handle!r}."

    name = data.get("displayName") or data.get("handle")
    lines = [
        f"{name} (@{data.get('handle')})",
        f"Followers: {_count(data.get('followersCount'))} · "
        f"Following: {_count(data.get('followsCount'))} · "
        f"Posts: {_count(data.get('postsCount'))}",
    ]
    bio = str(data.get("description") or "").strip()
    if bio:
        lines.append(f"\n{bio}")
    return format_untrusted("Bluesky profile", "\n".join(lines))


@tool_safe
def read_bluesky_feed(handle: str, limit: int = 10) -> str:
    """Read a user's recent *original* posts (reposts and replies filtered out). No key.

    Args:
        handle: A Bluesky handle, e.g. "user.bsky.social" (a leading @ is fine).
        limit: Number of original posts to return (1–25, default 10).
    """
    if not handle or not handle.strip():
        return "Provide a Bluesky handle, e.g. 'user.bsky.social'."
    try:
        n = max(1, min(int(limit), 25))
    except (TypeError, ValueError):
        return f"Invalid limit {limit!r}; provide a whole number (1–25)."

    data = fetch_json(
        f"{_XRPC}/app.bsky.feed.getAuthorFeed",
        source="Bluesky",
        # Server-side drop of replies; fetch extra to refill after dropping reposts.
        params={"actor": _handle(handle), "limit": min(n * 3, 100), "filter": "posts_no_replies"},
        timeout=15,
    )
    feed = data.get("feed") if isinstance(data, dict) else None
    if not isinstance(feed, list):
        return f"No posts found for {handle!r}."

    posts = []
    for item in feed:
        if not isinstance(item, dict) or item.get("reason"):  # reason == repost
            continue
        post = item.get("post")
        if not isinstance(post, dict):
            continue
        record = post.get("record")
        if not isinstance(record, dict) or record.get("reply"):  # belt-and-suspenders on replies
            continue
        text = str(record.get("text") or "").strip()
        if not text:
            continue
        posts.append(
            f"\n[{_fmt_dt(record.get('createdAt'))}] {text}"
            f"\n  ♥ {_count(post.get('likeCount'))} · ↻ {_count(post.get('repostCount'))}"
        )
        if len(posts) >= n:
            break

    if not posts:
        return f"No recent original posts by {handle!r} (they may only repost or reply)."
    return format_untrusted("Bluesky feed", f"Recent posts by @{_handle(handle)}:\n" + "\n".join(posts))
