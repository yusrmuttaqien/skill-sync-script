"""Normalization pass — before compare and before write.

Spec (Change sources & drift detection / Checks suite):
- line endings → LF
- BOM trimmed
- trailing newlines trimmed (file ends with exactly one \\n)
- leading `./` stripped from refs
"""

from __future__ import annotations

import re

# `./` at a path-token start: line start, or after whitespace / common delimiters.
_DOT_SLASH = re.compile(r"(^|[\s\"'`(=\[>])\./(?=[\w])", re.MULTILINE)


def normalize_text(text: str) -> str:
    """Idempotent normalization pass. Returns LF/BOM/trailing-newline/`./`-clean text."""
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _DOT_SLASH.sub(lambda m: m.group(1), text)
    text = text.rstrip("\n")
    return text + "\n"
