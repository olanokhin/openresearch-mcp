"""Smoke tests for read_repo and its URL parsing helpers."""
from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest
import requests as req_lib

from openresearch_mcp.tools.github import _parse_repo, read_repo


class TestParseRepo:
    def test_owner_slash_repo(self):
        assert _parse_repo("owner/repo") == ("owner", "repo")

    def test_full_github_url(self):
        assert _parse_repo("https://github.com/owner/repo") == ("owner", "repo")

    def test_git_suffix_stripped(self):
        assert _parse_repo("https://github.com/owner/repo.git") == ("owner", "repo")

    def test_shorthand_with_leading_whitespace(self):
        assert _parse_repo("  owner/repo  ") == ("owner", "repo")

    def test_non_github_host_raises(self):
        with pytest.raises(ValueError, match="GitHub"):
            _parse_repo("https://gitlab.com/owner/repo")

    def test_url_missing_repo_name_raises(self):
        with pytest.raises(ValueError, match="owner and repo"):
            _parse_repo("https://github.com/onlyowner")


class TestReadRepo:
    def _resp(self, data: dict) -> MagicMock:
        r = MagicMock()
        r.json.return_value = data
        r.raise_for_status.return_value = None
        return r

    def _meta(self, **overrides) -> dict:
        base = {
            "full_name": "owner/repo",
            "description": "A test repository",
            "language": "Python",
            "stargazers_count": 99,
            "default_branch": "main",
            "html_url": "https://github.com/owner/repo",
        }
        return {**base, **overrides}

    def test_returns_metadata_readme_and_file_tree(self):
        readme_b64 = base64.b64encode(b"# Project\nThis is the README.").decode()
        responses = [
            self._resp(self._meta()),
            self._resp({"content": readme_b64}),
            self._resp({"tree": [{"path": "src/main.py", "type": "blob"}]}),
        ]
        with patch("openresearch_mcp.tools.github.requests.get", side_effect=responses):
            result = read_repo("owner/repo")
        assert "owner/repo" in result
        assert "Python" in result
        assert "99" in result
        assert "This is the README." in result
        assert "src/main.py" in result

    def test_missing_readme_handled_gracefully(self):
        responses = [
            self._resp(self._meta()),
            MagicMock(**{"raise_for_status.side_effect": req_lib.HTTPError("404")}),
            self._resp({"tree": []}),
        ]
        with patch("openresearch_mcp.tools.github.requests.get", side_effect=responses):
            result = read_repo("owner/repo")
        assert "README" in result
        assert "Not found" in result

    def test_nonexistent_repo_returns_error_message(self):
        r = MagicMock()
        r.raise_for_status.side_effect = req_lib.HTTPError("404 Not Found")
        with patch("openresearch_mcp.tools.github.requests.get", return_value=r):
            result = read_repo("owner/doesnotexist")
        assert "not found" in result.lower() or "inaccessible" in result.lower()
