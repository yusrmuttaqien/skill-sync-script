"""Manifest — sync.json, the ONLY source of truth for what is synced.

Spec (Manifest): one file, JSON, human-readable.
Layout:
{
  "version": 1,
  "skills": {
    "<name>": {
      "targets": {
        "<target>": {"id": "<target-specific id>", "adopted": bool}
      }
    }
  }
}
"""

from __future__ import annotations

import json
from pathlib import Path

_VERSION = 1


def empty() -> dict:
    return {"version": _VERSION, "skills": {}}


def load(path: Path) -> dict:
    p = Path(path)
    if not p.exists():
        return empty()
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("version", _VERSION)
    data.setdefault("skills", {})
    return data


def save(path: Path, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


# --- per-skill accessors ---------------------------------------------------

def skill_entry(man: dict, name: str) -> dict:
    return man["skills"].setdefault(name, {"targets": {}})


def set_target(man: dict, name: str, target: str, target_id: str, adopted: bool = False) -> None:
    entry = skill_entry(man, name)
    entry["targets"][target] = {"id": target_id, "adopted": adopted}


def remove_target(man: dict, name: str, target: str) -> None:
    man["skills"].get(name, {}).get("targets", {}).pop(target, None)


def remove_skill(man: dict, name: str) -> None:
    man["skills"].pop(name, None)


def target_id(man: dict, name: str, target: str) -> str | None:
    return man["skills"].get(name, {}).get("targets", {}).get(target, {}).get("id")


def is_synced(man: dict, name: str, target: str) -> bool:
    return target_id(man, name, target) is not None


def is_adopted(man: dict, name: str, target: str) -> bool:
    return man["skills"].get(name, {}).get("targets", {}).get(target, {}).get("adopted", False)
