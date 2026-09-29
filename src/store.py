"""Store — the local normalization hub (plain directory).

Spec (Store / TUI scope #7):
- layout: <root>/skills/<name>/SKILL.md + companion files
- companion enumeration ignores config `ignore` patterns (default dotfiles)
- file modes preserved on every companion copy (store in/out)
- symlinks resolved to regular files on copy into the store
- create = template SKILL.md written BEFORE the editor launches
- post-edit (editor close) runs the full store-level Checks suite
"""

from __future__ import annotations

import fnmatch
import os
import shutil
from pathlib import Path

from .canonical import Bundle, canonical_text, parse_skill
from .checks import Context, POST_EDIT, run_checks
from .name import normalize_name

TEMPLATE = """---
name: {name}
description:
---

# {name}

Describe when the agent should use this skill.

Companion file references must be exact relative paths from this skill's
directory (e.g. `scripts/<file>.sh`) — no dot-slash prefixes, no bare filenames.
"""


class Store:
    def __init__(self, root: Path, ignore: list[str] | None = None):
        self.root = Path(root)
        self.skills_dir = self.root / "skills"
        self.ignore = ignore if ignore is not None else [".*"]

    # --- layout ---------------------------------------------------------

    def skill_dir(self, name: str) -> Path:
        return self.skills_dir / name

    def list_skills(self) -> list[str]:
        if not self.skills_dir.is_dir():
            return []
        return sorted(p.name for p in self.skills_dir.iterdir() if p.is_dir())

    # --- companion enumeration -------------------------------------------

    def _ignored(self, relpath: str) -> bool:
        parts = Path(relpath).parts
        return any(
            fnmatch.fnmatch(part, pat)
            for part in parts
            for pat in self.ignore
        )

    def read_companions(self, skill_dir: Path) -> tuple[dict[str, bytes], dict[str, int]]:
        """All companion files (SKILL.md excluded), ignore patterns applied.

        Symlinks are resolved to regular file contents (flattened).
        Returns (relpath → bytes, relpath → mode).
        """
        files: dict[str, bytes] = {}
        modes: dict[str, int] = {}
        for path in sorted(skill_dir.rglob("*")):
            if not path.is_file() or path.name == "SKILL.md":
                continue
            rel = path.relative_to(skill_dir).as_posix()
            if self._ignored(rel):
                continue
            files[rel] = path.read_bytes()  # follows symlinks → regular content
            modes[rel] = path.stat().st_mode & 0o777
        return files, modes

    # --- read / write ----------------------------------------------------

    def load(self, name: str) -> Bundle:
        d = self.skill_dir(name)
        text = (d / "SKILL.md").read_text(encoding="utf-8")
        companions, modes = self.read_companions(d)
        from .canonical import bundle_from_text

        return bundle_from_text(name, text, companions, modes)

    def save(self, name: str, bundle: Bundle) -> None:
        d = self.skill_dir(name)
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(canonical_text(bundle), encoding="utf-8")
        for rel, data in bundle.companions.items():
            path = d / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            mode = bundle.modes.get(rel)
            if mode is not None:
                os.chmod(path, mode)

    # --- create (template before editor) ----------------------------------

    def create(self, name: str) -> Path:
        """Write the template SKILL.md; returns its path (editor launches on it)."""
        name = normalize_name(name)
        d = self.skill_dir(name)
        if d.exists():
            raise FileExistsError(f"store skill exists: {name}")
        d.mkdir(parents=True, exist_ok=True)
        path = d / "SKILL.md"
        path.write_text(TEMPLATE.format(name=name), encoding="utf-8")
        return path

    def delete(self, name: str) -> None:
        shutil.rmtree(self.skill_dir(name))

    # --- post-edit (convergence point for store-level checks) -------------

    def context_for(self, name: str, **extra) -> Context:
        """Check context for one store skill (bundle + all store bundles)."""
        bundle = self.load(name)
        store_bundles = {n: self.load(n) for n in self.list_skills()}
        return Context(
            text=(self.skill_dir(name) / "SKILL.md").read_text(encoding="utf-8"),
            bundle=bundle,
            dir_name=name,
            store_bundles=store_bundles,
            **extra,
        )

    def post_edit(self, name: str, **extra) -> list:
        """Run the full store-level suite on editor close."""
        return run_checks(POST_EDIT, self.context_for(name, **extra))
