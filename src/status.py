"""Status — the join of store + adapters + manifest.

Per-cell states (spec legend):
  in-sync   ✓  managed, target normalized == last-synced blobs
  changed   ~  managed, target differs from last-synced blobs
  unmanaged +  on target, not in manifest
  to-add    +  in store, not on target
  offline   !  target unreachable
  error     !  per-skill read failed
  absent    —  nowhere
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import manifest as M
from .adapter import Adapter
from .links import to_relative
from .normalize import normalize_text
from .store import Store


@dataclass
class TargetState:
    target: str
    state: str
    target_id: str | None = None
    in_target: bool = False
    in_manifest: bool = False
    adopted: bool = False


@dataclass
class SkillStatus:
    name: str
    in_store: bool
    targets: list[TargetState] = field(default_factory=list)

    @property
    def state(self) -> str:
        if self.in_store and any(t.in_manifest for t in self.targets):
            return "synced"
        if self.in_store:
            return "local-only"
        if any(t.adopted for t in self.targets):
            return "adopted"
        return "target-only"


def _drift(adapter: Adapter, tid: str, blobs: dict[str, bytes], skill_dir) -> str:
    """normalize-then-exact-compare: target SKILL.md vs last-synced blob.

    Returns "in-sync", "changed", or "paths-stale" (text differs only in the
    absolute store prefix → the store moved, refs need repointing).
    """
    text, companions, _ = adapter.read_skill(tid)
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    target_text = normalize_text(text).encode("utf-8")
    if target_text != blobs.get("SKILL.md"):
        rel_target = to_relative(text, skill_dir)
        rel_blob = to_relative(blobs.get("SKILL.md", b"").decode("utf-8", "replace"), skill_dir)
        if normalize_text(rel_target).encode("utf-8") == normalize_text(rel_blob).encode("utf-8"):
            return "paths-stale"
        return "changed"
    if set(companions) != set(k for k in blobs if k != "SKILL.md"):
        return "changed"
    return "in-sync"


def compute_status(store: Store, adapters: dict[str, Adapter], man: dict) -> list[SkillStatus]:
    target_lists: dict[str, dict[str, str]] = {}
    offline: set[str] = set()
    for tid, adapter in adapters.items():
        try:
            target_lists[tid] = adapter.list_skills()
        except Exception:
            target_lists[tid] = {}
            offline.add(tid)

    names: set[str] = set(store.list_skills())
    for lst in target_lists.values():
        names.update(lst.keys())
    names.update(man["skills"].keys())
    store_names = set(store.list_skills())

    out: list[SkillStatus] = []
    for name in sorted(names):
        ts: list[TargetState] = []
        for tid, lst in target_lists.items():
            in_target = name in lst
            t = man["skills"].get(name, {}).get("targets", {}).get(tid)
            in_man = t is not None
            state = "absent"
            if tid in offline:
                state = "offline"
            elif in_target and in_man:
                blobs = M.get_blobs(man, name, tid)
                if blobs is None:
                    state = "unmanaged"
                else:
                    try:
                        state = _drift(adapters[tid], lst[name], blobs, store.skill_dir(name))
                    except Exception:
                        state = "error"
            elif in_target:
                state = "unmanaged"
            elif name in store_names:
                state = "to-add"
            ts.append(
                TargetState(
                    target=tid,
                    state=state,
                    target_id=lst.get(name),
                    in_target=in_target,
                    in_manifest=in_man,
                    adopted=bool(t and t.get("adopted")),
                )
            )
        out.append(SkillStatus(name=name, in_store=name in store_names, targets=ts))
    return out
