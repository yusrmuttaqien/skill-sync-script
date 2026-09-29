"""Config — single centralized config file.

Spec (Config section):
- Location: --config <path> flag; default = the store's directory
- Auto-generated with all defaults if no config file is found at that location
- --generate-config emits all keys with defaults + descriptions
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "config.json"

# Default config location: the project root (the directory containing src/).
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULTS: dict[str, Any] = {
    "store": {"path": "~/Documents/skill-sync/store"},
    "targets": {
        "pi": {"type": "pi", "skills_dir": "~/.pi/agent/skills"},
        "openwebui": {
            "type": "openwebui",
            "url": "http://localhost:30001",
            "api_key": "",
        },
        "obsidian": {
            "type": "obsidian",
            "skills_dir": "~/Documents/Obsidian/yusrmuttaqien-obsidian/📍 Guides/ai/skills",
            "default_tags": ["ai-chat"],
        },
    },
    "ignore": [".*"],
    "export": {"inline_threshold_bytes": 65536},
    "system": {"hostname": "macbook-pro", "open_terminal": True},
}

# Key descriptions for --generate-config output.
DESCRIPTIONS: dict[str, str] = {
    "store.path": "Store directory (canonical bundles live here)",
    "targets": "Named map of targets; each entry's `type` selects the adapter",
    "targets.*.type": "Adapter type: pi | openwebui | obsidian",
    "targets.pi.skills_dir": "pi agent skills directory",
    "targets.openwebui.url": "OpenWebUI base URL",
    "targets.openwebui.api_key": "Personal API key (sk- + 32 hex)",
    "targets.obsidian.skills_dir": "Obsidian skills folder (root of the skills area)",
    "targets.obsidian.default_tags": "Wrapper tags for newly exported skills",
    "ignore": "Globs ignored during companion enumeration (dotfiles by default)",
    "export.inline_threshold_bytes": "Companion size threshold for OWUI inline flatten",
    "system.hostname": "Hostname used in large-companion guide text",
    "system.open_terminal": "Which OWUI guide-text template to use",
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override onto base (override wins); dicts merge recursively."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def default_config() -> dict[str, Any]:
    import copy

    return copy.deepcopy(DEFAULTS)


def resolve_config_path(flag_path: str | Path | None) -> Path:
    """Config location: explicit flag, else <project root>/config.json."""
    if flag_path:
        return Path(flag_path).expanduser()
    return PROJECT_ROOT / CONFIG_FILENAME


def load_config(flag_path: str | Path | None = None) -> tuple[dict[str, Any], Path]:
    """Load config; auto-generate with defaults if missing.

    Returns (config, path).
    """
    path = resolve_config_path(flag_path)
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return _deep_merge(default_config(), loaded), path
    config = default_config()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_config(config, path)
    return config, path


def write_config(config: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def generate_config_text() -> str:
    """All keys with defaults + descriptions (--generate-config)."""
    lines = ["# skillsync config — all keys with defaults", ""]
    for key, description in DESCRIPTIONS.items():
        lines.append(f"# {key}: {description}")
    lines.append("")
    lines.append(json.dumps(DEFAULTS, indent=2, ensure_ascii=False))
    return "\n".join(lines) + "\n"
