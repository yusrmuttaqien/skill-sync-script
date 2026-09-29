"""Operations — adopt, rename, delete, batch.

Adopt: pull target skill into store, mark adopted (manifest).
Rename: move store dir + frontmatter name; cross-skill mentions checked
(RENAME_DELETE trigger).
Delete: remove from store + manifest; if it was synced, the caller is told
which targets to confirm deletion on.
Batch: apply an op to many skills, collect per-skill issues.
"""

from __future__ import annotations

import shutil

from . import manifest as M
from .adapter import Adapter
from .canonical import bundle_from_text, canonical_text, parse_skill
from .checks import Context, Issue, RENAME_DELETE, run_checks
from .name import normalize_name
from .store import Store
from .sync import import_skill


def adopt(store: Store, adapter: Adapter, man: dict, name: str) -> list:
    """Pull a target skill into the store and mark it adopted."""
    issues = import_skill(store, adapter, man, name)
    if not any(i.severity == "error" for i in issues):
        M.set_target(man, name, adapter.id, M.target_id(man, name, adapter.id) or name, adopted=True)
    return issues


def rename(store: Store, man: dict, old: str, new: str) -> list:
    """Rename a store skill (dir + frontmatter). Returns issues."""
    new = normalize_name(new)
    src, dst = store.skill_dir(old), store.skill_dir(new)
    if dst.exists():
        return [Issue("rename", "error", f"target skill exists: {new}")]
    shutil.move(str(src), str(dst))
    text = (dst / "SKILL.md").read_text(encoding="utf-8")
    fm, body = parse_skill(text)
    fm["name"] = new
    frontmatter = "\n".join(f"{k}: {v}" for k, v in fm.items() if v is not None)
    (dst / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n{body}", encoding="utf-8")
    bundle = store.load(new)
    ctx = Context(
        text=(dst / "SKILL.md").read_text(encoding="utf-8"),
        bundle=bundle,
        dir_name=new,
        store_bundles={n: store.load(n) for n in store.list_skills()},
        renamed_from=old,
    )
    issues = run_checks(RENAME_DELETE, ctx)
    # manifest: move the entry
    if old in man["skills"]:
        man["skills"][new] = man["skills"].pop(old)
    return issues


def delete_from_store(store: Store, man: dict, name: str) -> tuple[list, list[str]]:
    """Delete from store + manifest. Returns (issues, synced_targets)."""
    synced = [t for t in man["skills"].get(name, {}).get("targets", {})
              if M.target_id(man, name, t)]
    store.delete(name)
    M.remove_skill(man, name)
    return [], synced


def batch(fn, names: list[str], *args, **kwargs) -> dict[str, list]:
    """Apply fn(name, *args, **kwargs) to each name; collect issues per skill."""
    return {n: fn(n, *args, **kwargs) for n in names}
