"""Name normalization & identity charset.

Spec (Identity & rename):
- any input case accepted; always transformed to kebab-case
  (`My Cool_Skill!` → `my-cool-skill`)
- charset: letters (Unicode allowed), digits, hyphen — confusing symbols
  filtered, Unicode letters kept
"""

from __future__ import annotations

import re

_TOKEN_SPLIT = re.compile(r"[^\w]+|_+", re.UNICODE)  # non letter/digit runs AND underscores


def normalize_name(raw: str) -> str:
    """Any input → kebab-case identity name."""
    tokens = [t for t in _TOKEN_SPLIT.split(raw.strip()) if t]
    return "-".join(t.lower() for t in tokens)


def is_legal_name(name: str) -> bool:
    """Legal charset: Unicode letters, digits, hyphen; non-empty; no spaces."""
    if not name:
        return False
    return all(c.isalnum() or c == "-" for c in name)
