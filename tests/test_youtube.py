"""Smoke tests for get_youtube_transcript — covers URL variants and error paths."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from openresearch_mcp.tools.youtube import get_youtube_transcript

VIDEO_ID = "dQw4w9WgXcQ"


def _snippets(*texts: str) -> list[MagicMock]:
    snips = []
    for t in texts:
        s = MagicMock()
        s.text = t
        snips.append(s)
    return snips


class TestGetYoutubeTranscript:
    def test_full_watch_url(self):
        with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api:
            mock_api.return_value.fetch.return_value = _snippets("Hello", "world")
            result = get_youtube_transcript(f"https://www.youtube.com/watch?v={VIDEO_ID}")
        assert "Hello" in result
        assert "world" in result

    def test_youtu_be_short_url(self):
        with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api:
            mock_api.return_value.fetch.return_value = _snippets("Short link works")
            result = get_youtube_transcript(f"https://youtu.be/{VIDEO_ID}")
        assert "Short link works" in result

    def test_youtube_shorts_url(self):
        with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api:
            mock_api.return_value.fetch.return_value = _snippets("Shorts work")
            result = get_youtube_transcript(f"https://www.youtube.com/shorts/{VIDEO_ID}")
        assert "Shorts work" in result

    def test_bare_video_id(self):
        with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api:
            mock_api.return_value.fetch.return_value = _snippets("Bare ID accepted")
            result = get_youtube_transcript(VIDEO_ID)
        assert "Bare ID accepted" in result

    def test_snippets_joined_with_spaces(self):
        with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api:
            mock_api.return_value.fetch.return_value = _snippets("one", "two", "three")
            result = get_youtube_transcript(VIDEO_ID)
        assert "one two three" in result

    def test_invalid_url_raises_value_error(self):
        with pytest.raises(ValueError, match="Cannot extract"):
            get_youtube_transcript("not-a-youtube-url")

    def test_unavailable_transcript_returns_message(self):
        from youtube_transcript_api import CouldNotRetrieveTranscript
        with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api:
            mock_api.return_value.fetch.side_effect = CouldNotRetrieveTranscript(VIDEO_ID)
            result = get_youtube_transcript(VIDEO_ID)
        assert "unavailable" in result.lower()
