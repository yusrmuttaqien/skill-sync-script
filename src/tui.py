"""TUI — page-based flow (style ref: visref-canvas-builder).

Status page renders the store × targets table, then an arrow-key
select_menu drives the actions. Actions are their own prompt steps;
after each, back to the status page.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text

from . import manifest as M
from .adapter import make_adapter
from .canonical import canonical_text
from .config import load_config
from .name import normalize_name
from .normalize import normalize_text
from .operations import adopt, delete_from_store, rename
from .store import Store
from .status import compute_status
from .sync import export_skill, import_skill

console = Console()

MAX_DIFF_LINES = 40


def _diff_preview(old: str, new: str, old_label: str, new_label: str) -> str:
    import difflib

    lines = list(
        difflib.unified_diff(old.splitlines(), new.splitlines(), old_label, new_label, lineterm="")
    )
    if len(lines) > MAX_DIFF_LINES:
        lines = lines[:MAX_DIFF_LINES] + [f"\u2026 +{len(lines) - MAX_DIFF_LINES} more lines"]
    return "\n".join(lines) or "(no text change)"


def _companion_delta(old: dict, new: dict) -> list[str]:
    lines = []
    for rel in sorted(set(new) - set(old)):
        lines.append(f"[green]+ {rel}[/green]")
    for rel in sorted(set(old) - set(new)):
        lines.append(f"[red]- {rel}[/red]")
    return lines


def _confirm_apply(title: str, body: str, extra: list[str] | None = None) -> bool:
    console.print(Panel(body, title=title, border_style="yellow"))
    for line in extra or []:
        console.print(f"  {line}")
    ok = ask_confirm("Apply?")
    return False if ok is None else ok


# --- select_menu (ported from visref-canvas-builder) -----------------------

def select_menu(items, default=0):
    """Arrow-key navigable menu.

    items: list of (key, label, detail) tuples.
    Returns the chosen key, None when cancelled (Esc), or falls back to a
    plain prompt when stdin is not a TTY.
    """
    if not items:
        return None
    n = len(items)
    keys = [k for k, _, _ in items]

    def renderable(i):
        rows = []
        for j, (key, label, detail) in enumerate(items):
            suffix = f"  [dim]{detail}[/dim]" if detail else ""
            if j == i:
                rows.append(Text.from_markup(f"[bold cyan]\u25b8 {label}[/bold cyan]{suffix}"))
            else:
                rows.append(Text.from_markup(f"  {label}{suffix}"))
        rows.append(Text.from_markup(
            "[dim]\u2191/\u2193 navigate \u00b7 Enter select \u00b7 Esc back[/dim]"))
        return Group(*rows)

    try:
        is_tty = sys.stdin.isatty()
    except Exception:
        is_tty = False
    if not is_tty:
        from rich.prompt import Prompt

        return Prompt.ask("Select", choices=keys, show_choices=False)

    idx = max(0, min(default, n - 1))
    chosen = None

    if os.name == "posix":
        import select as _select
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        tty.setcbreak(fd)
    else:
        import msvcrt

        fd = None
        old = None

    try:
        with Live(renderable(idx), console=console, refresh_per_second=12, transient=True) as live:
            while chosen is None:
                if os.name == "posix":
                    r, _, _ = _select.select([fd], [], [], 0.2)
                    if not r:
                        continue
                    b = os.read(fd, 1)
                    if b == b"\x1b":
                        r2, _, _ = _select.select([fd], [], [], 0.05)
                        if not r2:
                            return None  # lone Esc -> cancel
                        b2 = os.read(fd, 1)
                        if b2 in (b"[", b"O"):
                            r3, _, _ = _select.select([fd], [], [], 0.05)
                            if r3:
                                b3 = os.read(fd, 1)
                                if b2 + b3 in (b"[A", b"OA"):
                                    idx = (idx - 1) % n
                                    live.update(renderable(idx))
                                elif b2 + b3 in (b"[B", b"OB"):
                                    idx = (idx + 1) % n
                                    live.update(renderable(idx))
                    elif b in (b"\r", b"\n"):
                        chosen = keys[idx]
                    elif b == b"\x03":
                        raise KeyboardInterrupt
                    else:
                        ch = b.decode("utf-8", errors="ignore").lower()
                        if len(ch) == 1 and ch in keys:
                            chosen = ch
                else:
                    b = msvcrt.getch()
                    if b in ("\xe0", "\x00"):
                        b2 = msvcrt.getch()
                        if b2 == "K":
                            idx = (idx - 1) % n
                            live.update(renderable(idx))
                        elif b2 == "J":
                            idx = (idx + 1) % n
                            live.update(renderable(idx))
                    elif b in ("\r", "\n"):
                        chosen = keys[idx]
                    elif b == "\x1b":
                        return None
                    else:
                        ch = b.lower()
                        if len(ch) == 1 and ch in keys:
                            chosen = ch
    finally:
        if os.name == "posix":
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except Exception:
                pass
    return chosen


# --- escapable prompts (Esc = cancel/back at every step) ----------------------

def _is_tty() -> bool:
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def ask_text(prompt: str, default: str | None = None) -> str | None:
    """Single-line input. Esc cancels (None). Non-TTY falls back to input()."""
    if not _is_tty():
        return input(f"{prompt}").strip() or default
    import select as _select
    import termios
    import tty

    console.print(prompt)
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    buf: list[str] = []
    try:
        while True:
            b = os.read(fd, 1)
            if b == b"\x1b":
                r, _, _ = _select.select([fd], [], [], 0.05)
                if not r:
                    return None  # lone Esc → cancel
            elif b in (b"\r", b"\n"):
                return "".join(buf) if buf else default
            elif b == b"\x03":
                raise KeyboardInterrupt
            elif b in (b"\x7f", b"\x08"):
                if buf:
                    buf.pop()
            else:
                buf.append(b.decode("utf-8", errors="ignore"))
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def ask_confirm(prompt: str, default: bool = True) -> bool | None:
    """y/n confirm — default in upper case (e.g. `[Y/n]`), Esc cancels (None).
    Non-TTY falls back to rich Confirm."""
    if not _is_tty():
        from rich.prompt import Confirm

        return Confirm.ask(prompt, default=default)
    import select as _select
    import termios
    import tty

    y, n = ("Y", "n") if default else ("y", "N")
    console.print(f"{prompt} [{y}/{n}]")
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    try:
        while True:
            b = os.read(fd, 1)
            if b in (b"y", b"Y"):
                return True
            if b in (b"n", b"N"):
                return False
            if b in (b"\r", b"\n"):
                return default
            if b == b"\x1b":
                r, _, _ = _select.select([fd], [], [], 0.05)
                if not r:
                    return None  # lone Esc → cancel
            if b == b"\x03":
                raise KeyboardInterrupt
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def select_multi(items):
    """Arrow-key multi-select. Space toggles, Enter confirms, Esc cancels.

    items: list of (key, label, detail). Returns the set of chosen keys
    (empty set = cancelled). Non-TTY falls back to a comma-separated prompt.
    """
    if not items:
        return set()
    keys = [k for k, _, _ in items]
    if not _is_tty():
        from rich.prompt import Prompt

        raw = Prompt.ask("Select (comma-separated, or 'all')")
        if raw.strip().lower() == "all":
            return set(keys)
        return {k.strip() for k in raw.split(",") if k.strip() in keys}

    import select as _select
    import termios
    import tty

    n = len(items)
    selected: set = set()
    idx = 0

    def renderable(i):
        rows = []
        for j, (key, label, detail) in enumerate(items):
            mark = "[bold green]x[/bold green]" if key in selected else " "
            suffix = f"  [dim]{detail}[/dim]" if detail else ""
            if j == i:
                rows.append(Text.from_markup(f"[bold cyan]\u25b8[/bold cyan] {mark} {label}{suffix}"))
            else:
                rows.append(Text.from_markup(f"    {mark} {label}{suffix}"))
        rows.append(Text.from_markup(
            "[dim]\u2191/\u2193 navigate \u00b7 space toggle \u00b7 Enter confirm \u00b7 Esc back[/dim]"))
        return Group(*rows)

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    try:
        with Live(renderable(idx), console=console, refresh_per_second=12, transient=True) as live:
            while True:
                if os.name == "posix":
                    r, _, _ = _select.select([fd], [], [], 0.2)
                    if not r:
                        continue
                    b = os.read(fd, 1)
                    if b == b"\x1b":
                        r2, _, _ = _select.select([fd], [], [], 0.05)
                        if not r2:
                            return set()  # lone Esc -> cancel
                        b2 = os.read(fd, 1)
                        if b2 in (b"[", b"O"):
                            r3, _, _ = _select.select([fd], [], [], 0.05)
                            if r3:
                                b3 = os.read(fd, 1)
                                if b2 + b3 in (b"[A", b"OA"):
                                    idx = (idx - 1) % n
                                    live.update(renderable(idx))
                                elif b2 + b3 in (b"[B", b"OB"):
                                    idx = (idx + 1) % n
                                    live.update(renderable(idx))
                    elif b in (b"\r", b"\n"):
                        return selected
                    elif b == b"\x03":
                        raise KeyboardInterrupt
                    elif b == b" ":
                        k = keys[idx]
                        selected.symmetric_difference_update({k})
                        live.update(renderable(idx))
                    else:
                        ch = b.decode("utf-8", errors="ignore").lower()
                        if len(ch) == 1 and ch in keys:
                            selected.symmetric_difference_update({ch})
                            live.update(renderable(idx))
                else:
                    raise NotImplementedError  # Windows: use the non-TTY path
    finally:
        if os.name == "posix":
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except Exception:
                pass


# --- editor ------------------------------------------------------------------

def _editor() -> list[str]:
    return os.environ.get("EDITOR", "vi").split()


def launch_editor(path: Path) -> None:
    subprocess.run(_editor() + [str(path)])


def _resolve_refs(store: Store, name: str, man: dict | None = None,
                  man_path=None) -> None:
    """P: per-occurrence ref decisions — create / rewrite / ignore.
    Ignores persist in the manifest (`ignored_refs`) for that skill."""
    import re as _re

    from .checks import ref_candidates
    from .normalize import normalize_text

    ignored = []
    if man is not None:
        ignored = man["skills"].get(name, {}).get("ignored_refs", [])

    d = store.skill_dir(name)
    path = d / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    bundle = store.load(name)
    cands = ref_candidates(text, bundle.companions if bundle else {}, ignored)
    if not cands:
        return
    console.print(Panel("[bold]ref candidates[/bold] — decide per occurrence",
                        title=name))
    for i, c in enumerate(cands):
        console.print(
            f"  {i + 1}. [{c.kind}] [bold]{c.token}[/bold] \u2192 {c.hint}  "
            f"[dim]\u00d7{c.count} \u00b7 {c.context}[/dim]"
        )
    def _ignore(token: str) -> None:
        nonlocal ignored
        if man is not None and man_path is not None and token not in ignored:
            entry = M.skill_entry(man, name)
            entry.setdefault("ignored_refs", []).append(token)
            ignored.append(token)
            M.save(man_path, man)
            console.print(f"  [dim]ignoring {token} (remembered)[/dim]")

    changed = False
    for i, c in enumerate(cands):
        choice = select_menu([
            ("c", f"{i + 1}. create {c.hint}", "empty file"),
            ("r", f"{i + 1}. rewrite \u2192 {c.hint}", f"replace {c.count} occurrence(s)"),
            ("i", f"{i + 1}. ignore", ""),
            ("a", f"ignore ALL {len(cands)} in this file", "remember all, on to the next skill"),
        ])
        if choice == "c":
            p = d / c.hint
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                p.write_bytes(b"")
                changed = True
                console.print(f"  [green]created {c.hint}[/green]")
        elif choice == "r":
            text = _re.sub(rf"(?<![\w./-]){_re.escape(c.token)}(?![\w])", c.hint, text)
            changed = True
            console.print(f"  [green]rewrote {c.token} \u2192 {c.hint}[/green]")
        elif choice == "a":
            for c2 in cands:
                _ignore(c2.token)
            break
        else:
            # None (Esc) or "i" → ignore, remembered for this skill
            _ignore(c.token)
    if changed:
        path.write_text(normalize_text(text), encoding="utf-8")


def prompt_edit_until_clean(store: Store, name: str, man: dict | None = None,
                            man_path=None) -> None:
    """After $EDITOR closes: run post-edit checks; loop until clean or kept."""
    while True:
        issues = store.post_edit(name)
        if not issues:
            return
        for i in issues:
            style = "red" if i.severity == "error" else "yellow"
            console.print(f" [{style}]{i.check}[/{style}] {i.message}")
        if any(i.check == "companion_ref_scan" for i in issues):
            _resolve_refs(store, name, man, man_path)
            continue  # re-check after the ref decisions
        keep = ask_confirm("Keep as-is (issues noted)?")
        if keep is None or keep:
            return  # Esc/cancel or yes → stop the edit loop
        launch_editor(store.skill_dir(name) / "SKILL.md")


# --- status page -------------------------------------------------------------

def _state_mark(state: str) -> str:
    return {
        "in-sync": "[green]in-sync[/green]",
        "changed": "[yellow]changed[/yellow]",
        "paths-stale": "[yellow]paths-stale[/yellow]",
        "unmanaged": "[cyan]unmanaged[/cyan]",
        "to-add": "[cyan]exportable[/cyan]",
        "offline": "[red]offline[/red]",
        "error": "[red]error[/red]",
        "absent": "[dim]absent[/dim]",
    }.get(state, "[dim]absent[/dim]")


LEGEND = (
    "[dim]legend: in-sync = target matches last sync · changed = target edited outside the tool · "
    "paths-stale = store moved, absolute refs need repoint · unmanaged = on target, not tracked · "
    "exportable = in store, ready to export to this target · offline = target unreachable · "
    "error = read failed · absent = nowhere[/dim]"
)


def render_status_table(store: Store, adapters: dict, man: dict) -> None:
    rows = compute_status(store, adapters, man)
    table = Table(title="[bold]skill-sync[/bold]")
    table.add_column("skill", header_style="bold")
    table.add_column("store")
    for tid in adapters:
        table.add_column(tid)
    for r in rows:
        cells = [r.name, "[green]in store[/green]" if r.in_store else "[dim]absent[/dim]"]
        for t in r.targets:
            cells.append(_state_mark(t.state))
        table.add_row(*cells)
    console.print(table)
    console.print(LEGEND)


def _pick_skill(names: list[str], in_store: set[str] | None = None):
    """select_menu over skill names; returns name or None."""
    items = [
        (n, n, "[dim]in store[/dim]" if in_store and n in in_store else "")
        for n in names
    ]
    return select_menu(items)


def _print_issues(issues) -> None:
    for i in issues:
        style = "red" if i.severity == "error" else "yellow"
        console.print(f"  [{style}]{i.check}[/{style}] {i.message}")


# --- actions (each returns to the status page) ---------------------------------

def _action_import(store, adapters, man, man_path, adopted: bool) -> None:
    targets = [(tid, tid, "") for tid in adapters]
    tid = select_menu(targets)
    if tid is None:
        return
    adapter = adapters[tid]
    full = adapter.list_skills_full()
    counts: dict[str, int] = {}
    for s in full:
        counts[s["name"]] = counts.get(s["name"], 0) + 1
    items = []
    for s in full:
        detail = ""
        if counts[s["name"]] > 1:
            detail = f"[dim]dup id: {s['id']}[/dim]"
        elif not s["is_active"]:
            detail = "[dim]inactive[/dim]"
        items.append((s["id"], s["name"], detail))
    tid_id = select_menu(items)
    if tid_id is None:
        return
    name = next(s["name"] for s in full if s["id"] == tid_id)
    # diff preview — the v1 guard (no in-TUI undo)
    ttext, tcomps, _ = adapter.read_skill(tid_id)
    if isinstance(ttext, bytes):
        ttext = ttext.decode("utf-8")
    # O: nameless/malformed → set name now
    name_override = None
    from .canonical import parse_skill

    fm, _ = parse_skill(ttext)
    if not fm.get("name"):
        from rich.prompt import Prompt

        given = ask_text("skill has no name — set it")
        if given is None:
            console.print("[dim]skipped[/dim]")
            return
        name_override = normalize_name(given)
        name = name_override
    existing = store.load(name)
    if existing:
        ok = _confirm_apply(
            f"import {name}: replace store copy",
            _diff_preview(
                canonical_text(existing), normalize_text(ttext),
                f"a/{name}/SKILL.md", f"b/{name}/SKILL.md",
            ),
            _companion_delta(existing.companions, tcomps),
        )
    else:
        ok = _confirm_apply(
            f"import {name}: will create",
            f"SKILL.md + {len(tcomps)} companion file(s)",
        )
    if not ok:
        console.print("[dim]skipped[/dim]")
        return
    issues = (
        adopt(store, adapter, man, name)
        if adopted
        else import_skill(store, adapter, man, name, target_id=tid_id, name_override=name_override)
    )
    _print_issues(issues)
    M.save(man_path, man)


def _action_export(store, adapters, man, man_path) -> None:
    names = store.list_skills()
    name = _pick_skill(names)
    if name is None:
        return
    tid = select_menu([(t, t, "") for t in adapters])
    if tid is None:
        return
    adapter = adapters[tid]
    bundle = store.load(name)
    # diff preview — the v1 guard (no in-TUI undo)
    existing_tid = M.target_id(man, name, tid) or adapter.list_skills().get(name)
    if existing_tid:
        ttext, tcomps, _ = adapter.read_skill(existing_tid)
        if isinstance(ttext, bytes):
            ttext = ttext.decode("utf-8")
        ok = _confirm_apply(
            f"export {name} \u2192 {tid}: replace target copy",
            _diff_preview(
                normalize_text(ttext), canonical_text(bundle),
                f"a/{name}/SKILL.md", f"b/{name}/SKILL.md",
            ),
            _companion_delta(tcomps, bundle.companions),
        )
    else:
        ok = _confirm_apply(
            f"export {name} \u2192 {tid}: will create",
            f"SKILL.md + {len(bundle.companions)} companion file(s)",
        )
    if not ok:
        console.print("[dim]skipped[/dim]")
        return
    issues = export_skill(store, adapter, man, name)
    _print_issues(issues)
    M.save(man_path, man)


def _action_rename(store, man, man_path) -> None:
    from rich.prompt import Prompt

    old = ask_text("from")
    if old is None:
        return
    new = ask_text("to")
    if new is None:
        return
    old, new = normalize_name(old), normalize_name(new)
    issues = rename(store, man, old, new)
    _print_issues(issues)
    M.save(man_path, man)


def _delete_from_target(store, adapters, man) -> None:
    """S: target-copy-only delete — store + other targets untouched."""
    names = store.list_skills()
    name = _pick_skill(names)
    if name is None:
        return
    tids = [tid for tid in adapters if M.target_id(man, name, tid)]
    if not tids:
        console.print("[dim]no target copies (nothing synced)[/dim]")
        return
    tid = select_menu([(t, t, "") for t in tids])
    if tid is None:
        return
    ok = ask_confirm(f"Delete {name} from {tid}? (store + other targets untouched)")
    if ok is None:
        console.print("[dim]cancelled[/dim]")
        return
    if not ok:
        return
    adapters[tid].delete_skill(M.target_id(man, name, tid) or name)
    console.print(f"[green]deleted {name} from {tid}[/green]")


def _action_delete(store, adapters, man, man_path) -> None:
    kind = select_menu([
        ("s", "Delete from store", "store identity; target copies become unmanaged"),
        ("t", "Delete from target", "that target's copy only (store untouched)"),
    ])
    if kind is None:
        return
    if kind == "t":
        _delete_from_target(store, adapters, man)
        return
    names = store.list_skills()
    name = _pick_skill(names)
    if name is None:
        return
    # confirm BEFORE deleting (Esc = cancel everything)
    synced = [
        t for t in man["skills"].get(name, {}).get("targets", {})
        if M.target_id(man, name, t)
    ]
    del_targets = False
    if synced:
        console.print(f"[yellow]also delete from: {', '.join(synced)}[/yellow]")
        r = ask_confirm("Delete from targets too?", default=False)
        if r is None:
            console.print("[dim]cancelled[/dim]")
            return
        del_targets = r
    delete_from_store(store, man, name)
    if del_targets:
        for tid in synced:
            adapters.get(tid) and adapters[tid].delete_skill(M.target_id(man, name, tid) or name)
    M.save(man_path, man)


def _action_create(store, man=None, man_path=None) -> None:
    from rich.prompt import Prompt

    name = ask_text("name")
    if name is None:
        return
    name = normalize_name(name)
    path = store.create(name)
    launch_editor(path)
    prompt_edit_until_clean(store, name, man, man_path)


def _action_scan(store, adapters, man=None, man_path=None) -> None:
    for name in store.list_skills():
        issues = store.post_edit(name)
        if issues:
            console.print(f"[yellow]{name}[/yellow]")
            _print_issues(issues)
            if any(i.check == "companion_ref_scan" for i in issues):
                _resolve_refs(store, name, man, man_path)
    for tid, adapter in adapters.items():
        unimp = adapter.list_unimportable()
        if unimp:
            console.print(f"[dim]{tid}: unimportable (no SKILL.md): {', '.join(unimp)}[/dim]")
        full = adapter.list_skills_full()
        counts: dict[str, int] = {}
        for s in full:
            counts[s["name"]] = counts.get(s["name"], 0) + 1
        dups = sorted(n for n, c in counts.items() if c > 1)
        if dups:
            console.print(f"[red]{tid}: duplicate names: {', '.join(dups)}[/red]")


def _repoint_one(store, adapters, man, name: str, tid: str) -> bool:
    """Repoint one skill × target. Returns True on success."""
    from .links import old_skill_prefix, to_absolute, to_relative
    from .normalize import normalize_text

    adapter = adapters[tid]
    tid_id = M.target_id(man, name, tid)
    if tid_id is None:
        return False
    try:
        text, comps, _ = adapter.read_skill(tid_id)
    except Exception:
        return False
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    blob_text = (M.get_blobs(man, name, tid) or {}).get("SKILL.md", b"").decode("utf-8", "replace")
    old = old_skill_prefix(text, name) or old_skill_prefix(blob_text, name)
    text = to_relative(normalize_text(text), store.skill_dir(name), [old] if old else [])
    text = to_absolute(text, store.skill_dir(name), comps)
    adapter.write_skill(tid_id, text, comps)
    ttext, tcomps, _ = adapter.read_skill(tid_id)
    if isinstance(ttext, bytes):
        ttext = ttext.decode("utf-8")
    M.set_target(
        man, name, tid, tid_id,
        adopted=M.is_adopted(man, name, tid),
        blobs={"SKILL.md": ttext.encode("utf-8"), **tcomps},
    )
    return True


def _action_repoint(store, adapters, man) -> None:
    """L: rewrite stale absolute store paths to the current store location."""
    names = [n for n in man["skills"] if n in store.list_skills()]
    scope = select_menu([
        ("s", "One skill", "pick skill → target"),
        ("a", "All skills", "every managed skill × target (store move)"),
    ])
    if scope is None:
        return
    if scope == "a":
        done, failed = 0, 0
        for name in names:
            for t in man["skills"].get(name, {}).get("targets", {}):
                if M.target_id(man, name, t) and t in adapters:
                    if _repoint_one(store, adapters, man, name, t):
                        done += 1
                    else:
                        failed += 1
        console.print(f"[green]repointed {done} skill(s)[/green]"
                     + (f" [red]{failed} failed[/red]" if failed else ""))
        return
    name = _pick_skill(names)
    if name is None:
        return
    managed = [t for t in man["skills"].get(name, {}).get("targets", {})
               if M.target_id(man, name, t) and t in adapters]
    tid = select_menu([(t, t, "") for t in managed]) if managed else None
    if tid is None:
        console.print("[dim]not managed on any target[/dim]")
        return
    if _repoint_one(store, adapters, man, name, tid):
        console.print(f"[green]repointed {name} on {tid}[/green]")
        return
    console.print("[red]repoint failed[/red]")


def _action_batch(store, adapters, man, man_path) -> None:
    kind = select_menu([
        ("i", "Batch Import", "target \u2192 store"),
        ("e", "Batch Export", "store \u2192 target"),
    ])
    if kind is None:
        return
    if kind == "i":
        tid = select_menu([(t, t, "") for t in adapters])
        if tid is None:
            return
        adapter = adapters[tid]
        full = adapter.list_skills_full()
        managed = {
            n for n, e in man["skills"].items()
            if tid in e.get("targets", {})
        }
        items = [
            (s["id"], s["name"],
             "" if s["name"] in managed else "[dim]unmanaged \u2014 adopt first[/dim]")
            for s in full
        ]
        chosen = select_multi(items)
        if not chosen:
            return
        names = [s["name"] for s in full if s["id"] in chosen and s["name"] in managed]
        skipped = len(chosen) - len(names)
        if not names:
            console.print("[yellow]no managed skills selected (unmanaged need Adopt first)[/yellow]")
            return
        note = f" ({skipped} unmanaged skipped)" if skipped else ""
        if not ask_confirm(f"Import {len(names)} skill(s) from {tid}?{note}"):
            return
        for name in names:
            issues = import_skill(store, adapter, man, name)
            if issues:
                console.print(f"[dim]{name}[/dim]")
                _print_issues(issues)
    else:
        names_all = store.list_skills()
        chosen = select_multi([(n, n, "") for n in names_all])
        if not chosen:
            return
        tid = select_menu([(t, t, "") for t in adapters])
        if tid is None:
            return
        names = [n for n in names_all if n in chosen]
        if not ask_confirm(f"Export {len(names)} skill(s) to {tid}?"):
            return
        for name in names:
            issues = export_skill(store, adapters[tid], man, name)
            if issues:
                console.print(f"[dim]{name}[/dim]")
                _print_issues(issues)
    M.save(man_path, man)


def _action_view(store, man=None, man_path=None) -> None:
    """N: store browser — view any file, edit SKILL.md via $EDITOR."""
    from rich.prompt import Prompt

    names = store.list_skills()
    name = _pick_skill(names)
    if name is None:
        return
    d = store.skill_dir(name)
    files = sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file())
    if len(files) == 1:
        f = files[0]  # nothing to choose
    else:
        f = select_menu([(f, f, "") for f in files])
        if f is None:
            return
    console.print(Panel((d / f).read_text(encoding="utf-8", errors="replace"), title=f))
    if ask_confirm("Edit SKILL.md? ($EDITOR)"):
        launch_editor(d / "SKILL.md")
        prompt_edit_until_clean(store, name, man, man_path)


# --- main loop -----------------------------------------------------------------

def run(config_path: str | None = None) -> None:
    from .config import resolve_config_path

    path = resolve_config_path(config_path)
    first_run = not path.exists()
    config, path = load_config(config_path)
    if first_run:
        # Q: onboarding — fill targets before the first scan
        console.print(Panel(
            f"Config generated with defaults at {path}.\n"
            "Fill in your targets (skills dirs, OWUI url + api_key).",
            title="first run",
        ))
        open_now = ask_confirm("Open config now? ($EDITOR)", default=True)
        if open_now is None:
            open_now = False
        if open_now:
            launch_editor(path)
            config, path = load_config(config_path)
    store = Store(Path(config["store"]["path"]).expanduser(), config.get("ignore"))
    man_path = Path(config["store"]["path"]).expanduser() / "sync.json"
    man = M.load(man_path)

    adapters = {}
    for tid in config.get("targets", {}):
        try:
            adapters[tid] = make_adapter(tid, config)
        except Exception as e:
            console.print(f"[yellow]target {tid} unavailable: {e}[/yellow]")

    while True:
        console.clear()
        render_status_table(store, adapters, man)
        choice = select_menu([
            ("i", "Import", "target \u2192 store \u00b7 target copy untouched"),
            ("e", "Export", "store \u2192 target"),
            ("a", "Adopt", "import + take over target copy (write-back)"),
            ("b", "Batch", "import/export a set at once"),
            ("r", "Rename", "store skill"),
            ("p", "Repoint", "fix stale absolute store paths"),
            ("d", "Delete", "from store and/or targets"),
            ("c", "Create", "new skill (template + $EDITOR)"),
            ("s", "Scan", "run checks on store"),
            ("v", "View", "store browser"),
            ("q", "Quit", ""),
        ])
        if choice is None:
            continue
        if choice == "q":
            console.print("[cyan]Goodbye![/cyan]")
            return
        try:
            if choice == "i":
                _action_import(store, adapters, man, man_path, adopted=False)
            elif choice == "e":
                _action_export(store, adapters, man, man_path)
            elif choice == "a":
                _action_import(store, adapters, man, man_path, adopted=True)
            elif choice == "r":
                _action_rename(store, man, man_path)
            elif choice == "d":
                _action_delete(store, adapters, man, man_path)
            elif choice == "c":
                _action_create(store, man, man_path)
            elif choice == "s":
                _action_scan(store, adapters, man, man_path)
            elif choice == "p":
                _action_repoint(store, adapters, man)
            elif choice == "b":
                _action_batch(store, adapters, man, man_path)
            elif choice == "v":
                _action_view(store, man, man_path)
        except KeyboardInterrupt:
            console.print("[yellow]Interrupted.[/yellow]")
