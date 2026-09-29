"""Link rewrite engine — relative ↔ absolute store-path references.

Export (store → pi/Obsidian): relative companion refs become absolute store
paths, so refs keep working from the target location.
Import (target → store): absolute store paths become relative again (the
streamlining).

Matching rule (spec): token-boundary (maximal path-like runs), exact
companion-rel match, skip URL/qualified contexts (a token preceded by `/`
or `:` is part of a URL/qualified name). Longest-first for the abs prefix.
"""

from __future__ import annotations

import re
from pathlib import Path

# maximal path-like run: segments of [A-Za-z0-9_-] joined by '/', ending in a
# dotted filename (no trailing dot). Lookbehind keeps us at token start.
_TOKEN = re.compile(r"(?<![A-Za-z0-9_.\-])(/?(?:[A-Za-z0-9_\-]+/)+[A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+)*)")


def _url_context(text: str, start: int) -> bool:
    return start > 0 and text[start - 1] in ("/", ":")


def to_absolute(text: str, skill_dir: Path, companions: dict) -> str:
    """Rewrite relative companion refs → absolute store paths."""
    abs_map = {rel: (skill_dir / rel).as_posix() for rel in companions}

    def repl(m):
        tok = m.group(1)
        if tok in abs_map and not _url_context(text, m.start()):
            return abs_map[tok]
        return tok

    return _TOKEN.sub(repl, text)


def to_relative(text: str, skill_dir: Path) -> str:
    """Rewrite absolute store paths under skill_dir → relative refs."""
    prefix = skill_dir.as_posix() + "/"

    def repl(m):
        tok = m.group(1)
        if tok.startswith(prefix) and not _url_context(text, m.start()):
            return tok[len(prefix):]
        return tok

    return _TOKEN.sub(repl, text)
