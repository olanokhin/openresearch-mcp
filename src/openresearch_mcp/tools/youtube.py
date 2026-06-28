"""YouTube transcript tool — no API key required."""

from __future__ import annotations

import re

from openresearch_mcp.constants import MAX_TEXT_CHARS
from openresearch_mcp.formatting import format_untrusted


def get_youtube_transcript(url: str) -> str:
    """Fetch the transcript/subtitles of a YouTube video. No API key required.

    Args:
        url: YouTube video URL (youtube.com/watch?v=..., youtu.be/..., shorts/) or bare 11-char video ID.
    """
    from youtube_transcript_api import CouldNotRetrieveTranscript, YouTubeTranscriptApi

    match = re.search(r"(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([a-zA-Z0-9_-]{11})", url)
    if match:
        video_id = match.group(1)
    elif re.fullmatch(r"[a-zA-Z0-9_-]{11}", url.strip()):
        video_id = url.strip()
    else:
        raise ValueError(f"Cannot extract a YouTube video ID from: {url!r}")

    try:
        transcript = YouTubeTranscriptApi().fetch(video_id, languages=("en", "en-US", "en-GB"))
    except CouldNotRetrieveTranscript as exc:
        return f"Transcript unavailable: {exc}"

    text = " ".join(snippet.text for snippet in transcript)[:MAX_TEXT_CHARS]
    return format_untrusted("YouTube transcript", text)
