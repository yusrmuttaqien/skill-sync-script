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

import base64
import hashlib
import json
from pathlib import Path

_VERSION = 1


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


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


def set_target(
    man: dict,
    name: str,
    target: str,
    target_id: str,
    adopted: bool = False,
    blobs: dict[str, bytes] | None = None,
) -> None:
    entry = skill_entry(man, name)
    t: dict = {"id": target_id, "adopted": adopted}
    if blobs is not None:
        t["blobs"] = {
            rel: (data.decode("utf-8") if rel == "SKILL.md" else _b64(data))
            for rel, data in blobs.items()
        }
    entry["targets"][target] = t


def get_blobs(man: dict, name: str, target: str) -> dict[str, bytes] | None:
    t = man["skills"].get(name, {}).get("targets", {}).get(target)
    if not t or "blobs" not in t:
        return None
    out: dict[str, bytes] = {}
    for rel, val in t["blobs"].items():
        out[rel] = val.encode("utf-8") if rel == "SKILL.md" else base64.b64decode(val)
    return out


def blob_hash(blobs: dict[str, bytes]) -> str:
    h = hashlib.sha256()
    for rel in sorted(blobs):
        h.update(rel.encode())
        h.update(blobs[rel])
    return h.hexdigest()


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


def target_blobs(man: dict, name: str, target: str) -> dict[str, bytes] | None:
    return get_blobs(man, name, target)
