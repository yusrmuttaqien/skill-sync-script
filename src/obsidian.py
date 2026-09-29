"""Obsidian adapter — flat .md notes, skill wrapped in an adaptive fence.

Note format (matches existing notes in the vault):
---
tags:
  - ai-chat
---
<````>
<entire skill: frontmatter + body>
<````>

Fence length = max(3, longest backtick run in the skill + 1) so the skill's
own code fences never leak. The note's own frontmatter carries the tags.
"""

from __future__ import annotations

import re

from .filesystem import FilesystemAdapter
from .name import normalize_name

_FENCE = re.compile(r"^`{3,}$")


def _fence_for(text: str) -> str:
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def unwrap(note: str) -> str:
    """Extract the fenced skill content from a note (raw text if no fence)."""
    lines = note.split("\n")
    for i, line in enumerate(lines):
        if _FENCE.fullmatch(line.strip()):
            fence = line.strip()
            for j in range(i + 1, len(lines)):
                if lines[j].strip() == fence:
                    return "\n".join(lines[i + 1 : j]) + "\n"
            break
    return note


def split_frontmatter(note: str) -> str | None:
    """The wrapper frontmatter block (including its `---` lines), or None."""
    lines = note.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[: i + 1])
    return None


class ObsidianAdapter(FilesystemAdapter):
    def __init__(self, root, id: str = "obsidian", tags: list[str] | None = None):
        super().__init__(root, id=id, layout="flat")
        self.tags = tags or []

    def wrap(self, text: str, existing_note: str | None = None) -> str:
        """Wrap skill in fence; pass-through existing wrapper frontmatter (G)."""
        fence = _fence_for(text)
        fm = split_frontmatter(existing_note) if existing_note else None
        if fm is None:
            tags = "".join(f"  - {t}\n" for t in self.tags)
            fm = f"---\ntags:\n{tags}---"
        return f"{fm}\n{fence}\n{text}{fence}\n"

    def _read_flat(self, target_id: str):
        note = self._file(target_id).read_text(encoding="utf-8")
        return unwrap(note).encode("utf-8"), {}, {}

    def _write_flat(self, target_id: str, text: str, companions: dict[str, bytes]) -> None:
        f = self._file(target_id)
        existing = f.read_text(encoding="utf-8") if f.exists() else None
        f.write_text(self.wrap(text, existing), encoding="utf-8")

    def _create_flat(self, name: str) -> str:
        from .filesystem import _MINIMAL

        target_id = normalize_name(name)
        f = self._file(target_id)
        if not f.exists():
            f.write_text(self.wrap(_MINIMAL.format(name=target_id)), encoding="utf-8")
        return target_id
