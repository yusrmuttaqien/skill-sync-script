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


def make_adapter(target_id: str) -> Adapter:
    cfg = _cfg.load()
    if target_id == "opencode":
        from .opencode import OpenCodeAdapter

        return OpenCodeAdapter(Path(cfg.get("targets", {}).get("opencode", {}).get("root", "")))
    if target_id == "openwebui":
        from .openwebui import OpenWebUIAdapter

        t = cfg.get("targets", {}).get("openwebui", {})
        return OpenWebUIAdapter(t.get("base_url", ""), t.get("api_key", ""))
    raise ValueError(f"unknown target: {target_id}")
