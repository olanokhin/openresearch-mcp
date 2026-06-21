"""GitHub repository reading tool. Works without a token; set GITHUB_TOKEN for 5k req/hr."""

from __future__ import annotations

import base64
import os
from urllib.parse import urlparse

import requests

GITHUB_API = "https://api.github.com"
GITHUB_RAW = "https://raw.githubusercontent.com"
MAX_TEXT_CHARS = 20_000
GITHUB_TEXT_FILES = {".md", ".rst", ".txt", ".toml", ".yaml", ".yml", ".json", ".py", ".js", ".ts"}


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "openresearch-mcp"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_json(url: str) -> dict | list:
    r = requests.get(url, headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json()


def _parse_repo(repo: str) -> tuple[str, str]:
    repo = repo.strip()
    if "://" not in repo and repo.count("/") >= 1:
        owner, name = repo.split("/")[:2]
        return owner, name.removesuffix(".git")
    parsed = urlparse(repo)
    if parsed.netloc not in {"github.com", "www.github.com"}:
        raise ValueError("Provide a GitHub URL or owner/repo name.")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError("GitHub URL must include owner and repo name.")
    return parts[0], parts[1].removesuffix(".git")


def _is_relevant(path: str) -> bool:
    lower = path.lower()
    if lower in {"pyproject.toml", "package.json", "requirements.txt", "setup.py", "readme.md", "readme.rst"}:
        return True
    if lower.startswith(("docs/", "doc/", "examples/", "example/")):
        return any(lower.endswith(ext) for ext in GITHUB_TEXT_FILES)
    return False


def read_repo(repo: str) -> str:
    """Read a public GitHub repository: metadata, README, file tree, and key files.

    Works without authentication (60 req/hr). Set GITHUB_TOKEN env var for 5,000 req/hr.

    Args:
        repo: GitHub repository URL (https://github.com/owner/repo) or owner/repo shorthand.
    """
    owner, name = _parse_repo(repo)
    api = f"{GITHUB_API}/repos/{owner}/{name}"
    try:
        meta = _get_json(api)
    except requests.HTTPError as exc:
        return f"Repository not found or inaccessible ({exc})."

    default_branch = meta.get("default_branch", "main")
    sections = [
        f"# {meta.get('full_name')}",
        f"Description: {meta.get('description')}",
        f"Language: {meta.get('language')} | Stars: {meta.get('stargazers_count')} | Branch: {default_branch}",
        f"URL: {meta.get('html_url')}",
    ]

    try:
        readme = _get_json(f"{api}/readme")
        text = base64.b64decode(readme.get("content", "")).decode("utf-8", errors="replace")
        sections.append(f"\n# README\n{text[:8000]}")
    except requests.HTTPError:
        sections.append("\n# README\nNot found.")

    tree = _get_json(f"{api}/git/trees/{default_branch}?recursive=1")
    paths = [item["path"] for item in (tree.get("tree", []) if isinstance(tree, dict) else []) if item.get("type") == "blob"]
    sections.append("\n# File tree\n" + "\n".join(paths[:200]))

    for path in [p for p in paths if _is_relevant(p)][:6]:
        try:
            r = requests.get(f"{GITHUB_RAW}/{owner}/{name}/{default_branch}/{path}", headers={"User-Agent": "openresearch-mcp"}, timeout=20)
            r.raise_for_status()
            content = r.text[:5000]
            sections.append(f"\n# {path}\n{content}")
        except requests.RequestException:
            continue

    return "\n".join(sections)[:MAX_TEXT_CHARS]
