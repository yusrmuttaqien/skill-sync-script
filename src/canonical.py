"""Canonical form — SKILL.md structure and the bundle.

Spec (Canonical form / Store):
- SKILL.md = frontmatter (`name`, `description`, … unknown fields pass
  through) + body
- links relative to the skill directory
- bundle = SKILL.md + companion files (single physical copy in the store)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml


@dataclass
class Bundle:
    """A skill in canonical form: frontmatter + body + companions."""

    name: str
    frontmatter: dict  # ordered: name, description, then unknown fields
    body: str
    companions: dict[str, bytes] = field(default_factory=dict)  # relpath → bytes
    modes: dict[str, int] = field(default_factory=dict)  # relpath → file mode (exec bits)

    @property
    def description(self) -> str:
        return str(self.frontmatter.get("description", ""))


def parse_skill(text: str) -> tuple[dict, str]:
    """Split SKILL.md text into (frontmatter, body). No frontmatter → ({}, text)."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return {}, text
    if not isinstance(data, dict):
        return {}, text
    return data, text[end + 5 :]


def serialize_skill(frontmatter: dict, body: str) -> str:
    """Frontmatter + body → SKILL.md text (key order preserved)."""
    fm = yaml.dump(frontmatter, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"---\n{fm}\n---\n{body}"


def bundle_from_text(
    name: str,
    text: str,
    companions: dict[str, bytes] | None = None,
    modes: dict[str, int] | None = None,
) -> Bundle:
    fm, body = parse_skill(text)
    # Reorder: name, description first, unknown fields keep their order.
    ordered: dict = {}
    for key in ("name", "description"):
        if key in fm:
            ordered[key] = fm.pop(key)
    ordered.update(fm)
    ordered.setdefault("name", name)
    return Bundle(
        name=name,
        frontmatter=ordered,
        body=body,
        companions=companions or {},
        modes=modes or {},
    )


def canonical_text(bundle: Bundle) -> str:
    return serialize_skill(bundle.frontmatter, bundle.body)
