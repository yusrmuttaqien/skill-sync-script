"""Adapter interface + factory.

Spec (Adapters): each target = list / read / write / delete / create,
flattened (symlinks resolved) reads, exec-bit preservation on writes.
"""

from __future__ import annotations

from pathlib import Path

from . import config as _cfg


class Adapter:
    """One target (OpenCode or OpenWebUI)."""

    id: str = ""

    def list_skills(self) -> dict[str, str]:
        """normalized name → target-specific id"""
        raise NotImplementedError

    def list_skills_full(self) -> list[dict]:
        """[{name, id, is_active}] — exposes duplicate names (spec H)."""
        return [
            {"name": n, "id": i, "is_active": True}
            for n, i in self.list_skills().items()
        ]

    def rename_on_target(self, old_id: str, new_name: str) -> str | None:
        """Recreate under a new id (rename); return new id, or None if unsupported."""
        return None

    def read_skill(self, target_id: str) -> tuple[bytes, dict[str, bytes], dict[str, int]]:
        """(SKILL.md bytes, companions relpath→bytes, relpath→mode) — symlinks resolved."""
        raise NotImplementedError

    def write_skill(self, target_id: str, text: str, companions: dict[str, bytes]) -> None:
        raise NotImplementedError

    def delete_skill(self, target_id: str) -> None:
        raise NotImplementedError

    def create_skill(self, name: str) -> str:
        """Create on the target (idempotent); return its id."""
        raise NotImplementedError


def make_adapter(target_name: str, cfg: dict) -> Adapter:
    """Build the adapter for a named target from config."""
    t = cfg["targets"][target_name]
    ttype = t.get("type", target_name)
    if ttype in ("pi", "filesystem"):
        from .filesystem import FilesystemAdapter

        return FilesystemAdapter(Path(t["skills_dir"]), id=target_name)
    if ttype == "obsidian":
        from .obsidian import ObsidianAdapter

        return ObsidianAdapter(
            Path(t["skills_dir"]), id=target_name, tags=t.get("default_tags")
        )
    if ttype == "openwebui":
        from .openwebui import OpenWebUIAdapter

        return OpenWebUIAdapter(
            t.get("url", ""),
            t.get("api_key", ""),
            inline_max_bytes=t.get("inline_max_bytes", 65536),
            store_path=Path(cfg["store"]["path"]).expanduser(),
        )
    raise ValueError(f"unknown target type: {ttype}")
