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


def ask_confirm(prompt: str, default: bool = False) -> bool | None:
    """y/n confirm. Esc cancels (None). Non-TTY falls back to rich Confirm."""
    if not _is_tty():
        from rich.prompt import Confirm

        return Confirm.ask(prompt, default=default)
    import select as _select
    import termios
    import tty

    d = "y" if default else "n"
    console.print(f"{prompt} [y/n] ({d})")
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


# --- editor ------------------------------------------------------------------

def _editor() -> list[str]:
    return os.environ.get("EDITOR", "vi").split()


def launch_editor(path: Path) -> None:
    subprocess.run(_editor() + [str(path)])


def prompt_edit_until_clean(store: Store, name: str) -> None:
    """After $EDITOR closes: run post-edit checks; loop until clean or kept."""
    while True:
        issues = store.post_edit(name)
        if not issues:
            return
        for i in issues:
            style = "red" if i.severity == "error" else "yellow"
            console.print(f" [{style}]{i.check}[/{style}] {i.message}")
        from rich.prompt import Confirm

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


def _action_delete(store, adapters, man, man_path) -> None:
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
        r = ask_confirm("Delete from targets too?")
        if r is None:
            console.print("[dim]cancelled[/dim]")
            return
        del_targets = r
    delete_from_store(store, man, name)
    if del_targets:
        for tid in synced:
            adapters.get(tid) and adapters[tid].delete_skill(M.target_id(man, name, tid) or name)
    M.save(man_path, man)


def _action_create(store) -> None:
    from rich.prompt import Prompt

    name = ask_text("name")
    if name is None:
        return
    name = normalize_name(name)
    path = store.create(name)
    launch_editor(path)
    prompt_edit_until_clean(store, name)


def _action_scan(store, adapters) -> None:
    for name in store.list_skills():
        issues = store.post_edit(name)
        if issues:
            console.print(f"[yellow]{name}[/yellow]")
            _print_issues(issues)
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


def _action_repoint(store, adapters, man) -> None:
    """L: rewrite stale absolute store paths to the current store location."""
    from .links import to_absolute, to_relative

    names = [n for n in man["skills"] if n in store.list_skills()]
    name = _pick_skill(names)
    if name is None:
        return
    managed = [t for t in man["skills"].get(name, {}).get("targets", {})
               if M.target_id(man, name, t) and t in adapters]
    tid = select_menu([(t, t, "") for t in managed]) if managed else None
    if tid is None:
        console.print("[dim]not managed on any target[/dim]")
        return
    adapter = adapters[tid]
    tid_id = M.target_id(man, name, tid)
    text, comps, _ = adapter.read_skill(tid_id)
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    from .normalize import normalize_text

    text = to_relative(normalize_text(text), store.skill_dir(name))
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
    console.print(f"[green]repointed {name} on {tid}[/green]")


def _action_view(store) -> None:
    """N: store browser — view any file."""
    from rich.prompt import Prompt

    names = store.list_skills()
    name = _pick_skill(names)
    if name is None:
        return
    d = store.skill_dir(name)
    files = sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file())
    console.print(f"[dim]{', '.join(files)}[/dim]")
    f = ask_text("file")
    if f is None or f not in files:
        return
    console.print(Panel((d / f).read_text(encoding="utf-8", errors="replace"), title=f))


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
            ("i", "Import", "target \u2192 store"),
            ("e", "Export", "store \u2192 target"),
            ("a", "Adopt", "import + mark adopted"),
            ("r", "Rename", "store skill"),
            ("p", "Repoint", "fix stale absolute store paths"),
            ("d", "Delete", "from store"),
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
                _action_create(store)
            elif choice == "s":
                _action_scan(store, adapters)
            elif choice == "p":
                _action_repoint(store, adapters, man)
            elif choice == "v":
                _action_view(store)
        except KeyboardInterrupt:
            console.print("[yellow]Interrupted.[/yellow]")
