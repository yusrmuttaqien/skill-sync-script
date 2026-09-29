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


def to_relative(text: str, skill_dir: Path, extra_prefixes: list[str] = ()) -> str:
    """Rewrite absolute store paths under skill_dir (or an extra prefix, e.g.
    the old store location after a move) → relative refs."""
    prefixes = [skill_dir.as_posix() + "/"] + [p + "/" for p in extra_prefixes]

    def repl(m):
        tok = m.group(1)
        for p in prefixes:
            if tok.startswith(p) and not _url_context(text, m.start()):
                return tok[len(p):]
        return tok

    return _TOKEN.sub(repl, text)


def old_skill_prefix(text: str, name: str) -> str | None:
    """The store skill-dir prefix embedded in a target text (may be stale
    after a store move). Returns e.g. `/old/root/store/skills/<name>`."""
    m = re.search(r"(/[\w.\-]+(?:/[\w.\-]+)*?/skills/" + re.escape(name) + r")/", text)
    return m.group(1) if m else None
