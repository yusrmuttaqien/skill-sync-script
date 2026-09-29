"""Status — the join of store + adapters + manifest (data only; TUI renders).

For every skill in the union of (store ∪ manifest ∪ each target),
compute presence per side. Categories:
- synced: in store AND in target AND in manifest
- local-only: in store, not in manifest for that target
- target-only: in target, not in store (unadopted)
- adopted: in target + manifest, not in store (adopted, not yet in store)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import manifest as M
from .adapter import Adapter
from .store import Store


@dataclass
class TargetState:
    target: str
    in_target: bool
    in_manifest: bool
    target_id: str | None = None
    adopted: bool = False


@dataclass
class SkillStatus:
    name: str
    in_store: bool
    targets: list[TargetState] = field(default_factory=list)

    @property
    def state(self) -> str:
        """Coarse category for display."""
        if self.in_store and any(t.in_manifest for t in self.targets):
            return "synced"
        if self.in_store:
            return "local-only"
        if any(t.in_manifest and t.adopted for t in self.targets):
            return "adopted"
        return "target-only"


def compute_status(store: Store, adapters: dict[str, Adapter], man: dict) -> list[SkillStatus]:
    # name → target_id per target (from the targets themselves);
    # one unreachable target must not crash the whole status
    target_lists: dict[str, dict[str, str]] = {}
    for tid, adapter in adapters.items():
        try:
            target_lists[tid] = adapter.list_skills()
        except Exception:
            target_lists[tid] = {}

    names: set[str] = set(store.list_skills())
    for tid, lst in target_lists.items():
        names.update(lst.keys())
    names.update(man["skills"].keys())

    out: list[SkillStatus] = []
    for name in sorted(names):
        ts: list[TargetState] = []
        for tid, lst in target_lists.items():
            in_target = name in lst
            in_man = M.is_synced(man, name, tid)
            ts.append(
                TargetState(
                    target=tid,
                    in_target=in_target,
                    in_manifest=in_man,
                    target_id=lst.get(name),
                    adopted=M.is_adopted(man, name, tid),
                )
            )
        out.append(SkillStatus(name=name, in_store=name in store.list_skills(), targets=ts))
    return out
