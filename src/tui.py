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
from rich.table import Table
from rich.text import Text

from . import manifest as M
from .adapter import make_adapter
from .config import load_config
from .name import normalize_name
from .operations import adopt, delete_from_store, rename
from .store import Store
from .status import compute_status
from .sync import export_skill, import_skill

console = Console()


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

        if Confirm.ask("Keep as-is (issues noted)?", default=False):
            return
        launch_editor(store.skill_dir(name) / "SKILL.md")


# --- status page -------------------------------------------------------------

def _state_mark(in_store: bool, in_target: bool) -> str:
    if in_store and in_target:
        return "[green]synced[/green]"
    if in_store:
        return "[yellow]local[/yellow]"
    if in_target:
        return "[cyan]target[/cyan]"
    return "[dim]\u2014[/dim]"


def render_status_table(store: Store, adapters: dict, man: dict) -> None:
    rows = compute_status(store, adapters, man)
    table = Table(title="[bold]skill-sync[/bold]")
    table.add_column("skill", header_style="bold")
    table.add_column("store")
    for tid in adapters:
        table.add_column(tid)
    for r in rows:
        cells = [r.name, "[green]\u2713[/green]" if r.in_store else "[dim]\u2014[/dim]"]
        for t in r.targets:
            cells.append(_state_mark(r.in_store, t.in_target))
        table.add_row(*cells)
    console.print(table)


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
    names = list(adapter.list_skills())
    name = _pick_skill(names)
    if name is None:
        return
    issues = adopt(store, adapter, man, name) if adopted else import_skill(store, adapter, man, name)
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
    issues = export_skill(store, adapters[tid], man, name)
    _print_issues(issues)
    M.save(man_path, man)


def _action_rename(store, man, man_path) -> None:
    from rich.prompt import Prompt

    old = normalize_name(Prompt.ask("from"))
    new = normalize_name(Prompt.ask("to"))
    issues = rename(store, man, old, new)
    _print_issues(issues)
    M.save(man_path, man)


def _action_delete(store, adapters, man, man_path) -> None:
    names = store.list_skills()
    name = _pick_skill(names)
    if name is None:
        return
    _, synced = delete_from_store(store, man, name)
    if synced:
        from rich.prompt import Confirm

        console.print(f"[yellow]also delete from: {', '.join(synced)}[/yellow]")
        if Confirm.ask("Delete from targets?", default=False):
            for tid in synced:
                adapters.get(tid) and adapters[tid].delete_skill(M.target_id(man, name, tid) or name)
    M.save(man_path, man)


def _action_create(store) -> None:
    from rich.prompt import Prompt

    name = normalize_name(Prompt.ask("name"))
    path = store.create(name)
    launch_editor(path)
    prompt_edit_until_clean(store, name)


def _action_scan(store) -> None:
    for name in store.list_skills():
        issues = store.post_edit(name)
        if issues:
            console.print(f"[yellow]{name}[/yellow]")
            _print_issues(issues)


# --- main loop -----------------------------------------------------------------

def run(config_path: str | None = None) -> None:
    config, _ = load_config(config_path)
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
            ("d", "Delete", "from store"),
            ("c", "Create", "new skill (template + $EDITOR)"),
            ("s", "Scan", "run checks on store"),
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
                _action_scan(store)
        except KeyboardInterrupt:
            console.print("[yellow]Interrupted.[/yellow]")
