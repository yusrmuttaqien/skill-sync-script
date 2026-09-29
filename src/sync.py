"""Import / Export — the two sync directions.

Import (target → store): read target, normalize, run import checks, save to
store, mark manifest.
Export (store → target): load store bundle, write canonical text + companions
to target (creating it there if absent), mark manifest.

Both return issues; the caller (TUI) decides prompting. `strict=True`
blocks on error-severity issues.
"""

from __future__ import annotations

from . import manifest as M
from .adapter import Adapter
from .canonical import Bundle, bundle_from_text, canonical_text
from .checks import Context, IMPORT, run_checks
from .normalize import normalize_text
from .store import Store


def _target_id(adapter: Adapter, man: dict, name: str) -> str:
    tid = M.target_id(man, name, adapter.id)
    if tid is not None:
        return tid
    lst = adapter.list_skills()
    if name in lst:
        return lst[name]
    raise KeyError(f"skill {name!r} not found on target {adapter.id}")


def import_skill(store: Store, adapter: Adapter, man: dict, name: str, strict: bool = True) -> list:
    """Pull one skill from target into the store. Returns issues."""
    tid = _target_id(adapter, man, name)
    text, companions, modes = adapter.read_skill(tid)
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    text = normalize_text(text)
    bundle = bundle_from_text(name, text, companions, modes)
    ctx = Context(text=text, bundle=bundle, dir_name=name)
    issues = run_checks(IMPORT, ctx)
    if strict and any(i.severity == "error" for i in issues):
        return issues  # do not import a broken skill
    store.save(name, bundle)
    M.set_target(
        man, name, adapter.id, tid,
        blobs={"SKILL.md": text.encode("utf-8"), **{k: v for k, v in bundle.companions.items()}},
    )
    return issues


def export_skill(store: Store, adapter: Adapter, man: dict, name: str) -> list:
    """Push one store skill to the target. Returns issues (store-level)."""
    bundle = store.load(name)
    issues = store.post_edit(name)
    if any(i.severity == "error" for i in issues):
        return issues
    tid = M.target_id(man, name, adapter.id)
    if tid is None:
        # not on target yet → find by name, else create
        tid = adapter.list_skills().get(name) or adapter.create_skill(name)
    text = canonical_text(bundle)
    adapter.write_skill(tid, text, bundle.companions)
    M.set_target(
        man, name, adapter.id, tid,
        blobs={"SKILL.md": text.encode("utf-8"), **bundle.companions},
    )
    return issues
