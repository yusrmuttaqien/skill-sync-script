"""skillsync entry point.

Default (no flags): the TUI. Flags: --generate-config, --config, --version.
"""

from __future__ import annotations

import argparse

from importlib.metadata import PackageNotFoundError, version

from src.config import generate_config_text, load_config

try:
    __version__ = version("skillsync")
except PackageNotFoundError:  # running from a checkout without install
    __version__ = "0.0.0+local"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillsync",
        description="Centralized skill management across pi, OpenWebUI, and Obsidian",
    )
    parser.add_argument("--version", action="version", version=f"skillsync {__version__}")
    parser.add_argument("--config", help="Config file path (default: <project root>/config.json)")
    parser.add_argument(
        "--generate-config",
        action="store_true",
        help="Emit all keys with defaults + descriptions",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.generate_config:
        print(generate_config_text())
        return 0

    from .tui import run as tui_run

    tui_run(args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
