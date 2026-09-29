"""TUI — rich-based interface.

Screens: status table (store × targets), actions (import/export/adopt/
rename/delete/create/scan), $EDITOR launch with post-edit check prompting.
Input-driven: single keys at the prompt.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import manifest as M
from .adapter import make_adapter
from .config import load_config
from .name import normalize_name
from .operations import adopt, delete_from_store, rename
from .store import Store
from .status import compute_status
from .sync import export_skill, import_skill

HELP = """[b]keys[/b]
  i import   e export   a adopt    r rename
  d delete   c create   s scan     q quit
"""


def _editor() -> list[str]:
    return os.environ.get("EDITOR", "vi").split()


def launch_editor(console: Console, path: Path) -> None:
    subprocess.run(_editor() + [str(path)])


def _state_mark(in_a: bool, in_b: bool) -> str:
    if in_a and in_b:
        return "[green]synced[/green]"
    if in_a:
        return "[yellow]local[/yellow]"
    if in_b:
        return "[cyan]target[/cyan]"
    return "[dim]—[/dim]"


def render_status(console: Console, store: Store, adapters: dict, man: dict) -> None:
    rows = compute_status(store, adapters, man)
    table = Table(title="skill-sync status")
    table.add_column("skill")
    table.add_column("store")
    for tid in adapters:
        table.add_column(tid)
    for r in rows:
        cells = [r.name, "[green]✓[/green]" if r.in_store else "[dim]—[/dim]"]
        for t in r.targets:
            cells.append(_state_mark(r.in_store, t.in_target))
        table.add_row(*cells)
    console.clear()
    console.print(table)
    console.print(Panel(HELP, border_style="dim"))


def prompt_edit_until_clean(console: Console, store: Store, name: str) -> None:
    """After $EDITOR closes: run post-edit checks; loop until clean or kept."""
    while True:
        issues = store.post_edit(name)
        if not issues:
            return
        for i in issues:
            style = "red" if i.severity == "error" else "yellow"
            console.print(f" [{style}]{i.check}[/{style}] {i.message}")
        ans = console.input(" [e]dit again / [k]eep / [b]ack (revert next save): ").strip().lower()
        if ans == "k":
            return
        if ans == "b":
            return
        launch_editor(console, store.skill_dir(name) / "SKILL.md")


def run(config_path: str | None = None) -> None:
    config, _ = load_config(config_path)
    console = Console()
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
        render_status(console, store, adapters, man)
        key = console.input("> ").strip().lower()
        if key == "q":
            break
        if key in ("i", "e", "a"):
            name = normalize_name(console.input(" skill: "))
            if key == "i":
                for tid, a in adapters.items():
                    if name in a.list_skills():
                        issues = import_skill(store, a, man, name)
                        for i in issues:
                            console.print(f"[yellow]{i.check}[/yellow] {i.message}")
                        break
            elif key == "e":
                for tid, a in adapters.items():
                    issues = export_skill(store, a, man, name)
                    for i in issues:
                        console.print(f"[red]{i.check}[/red] {i.message}")
            else:
                for tid, a in adapters.items():
                    if name in a.list_skills():
                        issues = adopt(store, a, man, name)
                        for i in issues:
                            console.print(f"[yellow]{i.check}[/yellow] {i.message}")
                        break
            M.save(man_path, man)
        elif key == "r":
            old = normalize_name(console.input(" from: "))
            new = normalize_name(console.input(" to: "))
            issues = rename(store, man, old, new)
            for i in issues:
                console.print(f"[yellow]{i.check}[/yellow] {i.message}")
            M.save(man_path, man)
        elif key == "d":
            name = normalize_name(console.input(" skill: "))
            _, synced = delete_from_store(store, man, name)
            if synced:
                console.print(f"[yellow]also delete from: {', '.join(synced)}?[/yellow] ")
                if console.input(" y/n: ").strip().lower() == "y":
                    for tid in synced:
                        a = adapters.get(tid)
                        if a:
                            a.delete_skill(M.target_id(man, name, tid) or name)
            M.save(man_path, man)
        elif key == "c":
            name = normalize_name(console.input(" name: "))
            path = store.create(name)
            launch_editor(console, path)
            prompt_edit_until_clean(console, store, name)
        elif key == "s":
            for name in store.list_skills():
                issues = store.post_edit(name)
                if issues:
                    console.print(f"[yellow]{name}[/yellow]")
                    for i in issues:
                        style = "red" if i.severity == "error" else "yellow"
                        console.print(f"  [{style}]{i.check}[/{style}] {i.message}")
        else:
            console.print("[dim]unknown key[/dim]")
