"""Shared limits for tool output.

Single source of truth for caps that were previously duplicated across tool
modules. As new domains land (roadmap 0.2.0+), reuse these instead of redefining
a per-tool ``MAX_TEXT_CHARS`` — that drift is exactly what this module prevents.
"""

from __future__ import annotations

# Hard cap on the characters any single tool returns to the agent. Keeps a large
# page/PDF/repo from blowing the context window; tools truncate to this.
MAX_TEXT_CHARS = 20_000
