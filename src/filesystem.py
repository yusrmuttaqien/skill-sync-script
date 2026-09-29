"""Filesystem adapter — any directory-based target (pi, obsidian, ...).

Spec: skills live in <root>/<name>/SKILL.md (+ companions).
Create: dir + minimal SKILL.md, idempotent.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .adapter import Adapter
from .name import normalize_name

_MINIMAL = """---
name: {name}
description:
---
"""


class FilesystemAdapter(Adapter):
    def __init__(self, root: Path, id: str = "filesystem"):
        self.id = id
        self.root = Path(root).expanduser()

    def _dir(self, target_id: str) -> Path:
        return self.root / target_id

    def list_skills(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if not self.root.is_dir():
            return out
        for d in sorted(self.root.iterdir()):
            if d.is_dir() and (d / "SKILL.md").is_file():
                out[normalize_name(d.name)] = d.name
        return out

    def read_skill(self, target_id: str) -> tuple[bytes, dict[str, bytes], dict[str, int]]:
        d = self._dir(target_id)
        text = (d / "SKILL.md").read_bytes()
        companions: dict[str, bytes] = {}
        modes: dict[str, int] = {}
        for p in sorted(d.rglob("*")):
            if not p.is_file() or p.name == "SKILL.md":
                continue
            rel = p.relative_to(d).as_posix()
            companions[rel] = p.read_bytes()  # follows symlinks → resolved
            modes[rel] = p.stat().st_mode & 0o777
        return text, companions, modes

    def write_skill(self, target_id: str, text: str, companions: dict[str, bytes]) -> None:
        d = self._dir(target_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(text, encoding="utf-8")
        for rel, data in companions.items():
            p = d / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)

    def delete_skill(self, target_id: str) -> None:
        shutil.rmtree(self._dir(target_id))

    def create_skill(self, name: str) -> str:
        target_id = normalize_name(name)
        d = self._dir(target_id)
        d.mkdir(parents=True, exist_ok=True)
        skill = d / "SKILL.md"
        if not skill.exists():
            skill.write_text(_MINIMAL.format(name=target_id), encoding="utf-8")
        return target_id
