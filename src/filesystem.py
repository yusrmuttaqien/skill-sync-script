"""Filesystem adapter — any directory-based target (pi, obsidian, ...).

Layouts:
- dir (pi):  <root>/<name>/SKILL.md (+ companions, exec bits preserved)
- flat (obsidian): <root>/<name>.md — one file per skill, no companions
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
    def __init__(self, root: Path, id: str = "filesystem", layout: str = "dir"):
        self.id = id
        self.root = Path(root).expanduser()
        self.layout = layout

    # --- dir layout --------------------------------------------------------

    def _dir(self, target_id: str) -> Path:
        return self.root / target_id

    def _list_dir(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if not self.root.is_dir():
            return out
        for d in sorted(self.root.iterdir()):
            if d.is_dir() and (d / "SKILL.md").is_file():
                out[normalize_name(d.name)] = d.name
        return out

    def _read_dir(self, target_id: str) -> tuple[bytes, dict[str, bytes], dict[str, int]]:
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

    def _write_dir(self, target_id: str, text: str, companions: dict[str, bytes]) -> None:
        d = self._dir(target_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(text, encoding="utf-8")
        for rel, data in companions.items():
            p = d / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)

    def _delete_dir(self, target_id: str) -> None:
        shutil.rmtree(self._dir(target_id))

    def _create_dir(self, name: str) -> str:
        target_id = normalize_name(name)
        d = self._dir(target_id)
        d.mkdir(parents=True, exist_ok=True)
        skill = d / "SKILL.md"
        if not skill.exists():
            skill.write_text(_MINIMAL.format(name=target_id), encoding="utf-8")
        return target_id

    # --- flat layout ---------------------------------------------------------

    def _file(self, target_id: str) -> Path:
        return self.root / f"{target_id}.md"

    def _list_flat(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if not self.root.is_dir():
            return out
        for p in sorted(self.root.glob("*.md")):
            if not p.name.startswith("."):
                out[normalize_name(p.stem)] = p.stem
        return out

    def _read_flat(self, target_id: str) -> tuple[bytes, dict[str, bytes], dict[str, int]]:
        return self._file(target_id).read_bytes(), {}, {}

    def _write_flat(self, target_id: str, text: str, companions: dict[str, bytes]) -> None:
        self._file(target_id).write_text(text, encoding="utf-8")

    def _delete_flat(self, target_id: str) -> None:
        self._file(target_id).unlink(missing_ok=True)

    def _create_flat(self, name: str) -> str:
        target_id = normalize_name(name)
        f = self._file(target_id)
        if not f.exists():
            f.write_text(_MINIMAL.format(name=target_id), encoding="utf-8")
        return target_id

    # --- dispatch ------------------------------------------------------------

    def list_skills(self) -> dict[str, str]:
        return self._list_flat() if self.layout == "flat" else self._list_dir()

    def read_skill(self, target_id: str) -> tuple[bytes, dict[str, bytes], dict[str, int]]:
        return self._read_flat(target_id) if self.layout == "flat" else self._read_dir(target_id)

    def write_skill(self, target_id: str, text: str, companions: dict[str, bytes]) -> None:
        (self._write_flat if self.layout == "flat" else self._write_dir)(target_id, text, companions)

    def delete_skill(self, target_id: str) -> None:
        (self._delete_flat if self.layout == "flat" else self._delete_dir)(target_id)

    def create_skill(self, name: str) -> str:
        return self._create_flat(name) if self.layout == "flat" else self._create_dir(name)
