"""OpenResearch MCP — zero-auth multi-source research server."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Single source of truth: read from installed package metadata so __version__
    # can never drift from pyproject.toml again.
    __version__ = version("openresearch-mcp")
except PackageNotFoundError:  # pragma: no cover - only when running from a raw checkout
    __version__ = "0.0.0+unknown"
