"""skillsync entry point.

Phase 0: config loading + generate-config. The TUI lands in Phase 7;
until then the entry point prints a plain-text config summary.
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
    parser.add_argument("--config", help="Config file path (default: <store dir>/config.json)")
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

    config, path = load_config(args.config)
    print(f"skillsync {__version__}")
    print(f"config: {path}")
    print(f"store:  {config['store']['path']}")
    for name, target in config["targets"].items():
        print(f"target: {name} ({target['type']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
