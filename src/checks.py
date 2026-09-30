"""Checks — canonical suite.

Spec (Checks): one registerable list; meta-rule: a new check is registered
here and wired to its triggers.

Triggers: post_edit (store, incl. create), import, scan, rename_delete.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .canonical import Bundle, parse_skill
from .name import is_legal_name
from .normalize import normalize_text

POST_EDIT = "post_edit"
IMPORT = "import"
SCAN = "scan"
RENAME_DELETE = "rename_delete"


@dataclass
class Context:
    """What a check run can see. All fields optional per trigger."""

    text: str | None = None  # raw SKILL.md text under check
    bundle: Bundle | None = None
    dir_name: str | None = None  # store dir name (store integrity)
    store_bundles: dict[str, Bundle] = field(default_factory=dict)  # name → bundle
    renamed_from: str | None = None  # old name (cross-skill mentions)
    target_names: list[tuple[str, str]] | None = None  # (normalized name, target id)


@dataclass
class Issue:
    check: str
    severity: str  # "error" | "warn"
    message: str


@dataclass
class RefCandidate:
    """One per-occurrence ref decision (spec P): token + context + hint."""

    token: str  # the occurrence text
    hint: str  # suggested relative path
    kind: str  # "broken" (path token, no file) | "bare" (basename of a companion)
    context: str  # the line it occurs on
    count: int  # occurrences


def ref_candidates(text: str, companions: dict, ignored: list[str] = ()) -> list["RefCandidate"]:
    """Extract per-occurrence ref candidates from SKILL.md text.
    `ignored` = tokens the user already decided to ignore (persisted)."""
    out: list[RefCandidate] = []
    lines = text.split("\n")
    ignored = set(ignored)

    def _context(token: str) -> str:
        for line in lines:
            if token in line:
                return line.strip()[:80]
        return ""

    # broken: path-looking tokens with no matching companion
    for token in re.findall(r"(?<![\w./-])((?:[\w.-]+/)+[\w.-]+)", text):
        if token not in companions and token not in ignored:
            out.append(RefCandidate(token, token, "broken", _context(token), text.count(token)))
    # bare: companion basename used without its dir part
    for relpath in companions:
        if "/" not in relpath:
            continue
        basename = relpath.rsplit("/", 1)[-1]
        if basename not in ignored and re.search(rf"(?<![\w/]){re.escape(basename)}(?![\w])", text):
            out.append(RefCandidate(basename, relpath, "bare", _context(basename), len(re.findall(rf"(?<![\w/]){re.escape(basename)}(?![\w])", text))))
    return out


def _frontmatter_valid(ctx: Context) -> list[Issue]:
    if ctx.text is None:
        return []
    fm, _ = parse_skill(ctx.text)
    if not fm:
        return [Issue("frontmatter_valid", "error", "frontmatter missing or unparseable")]
    name = str(fm.get("name", ""))
    if not name:
        return [Issue("frontmatter_valid", "error", "`name` missing")]
    if not is_legal_name(name):
        return [Issue("frontmatter_valid", "error", f"`name` has illegal charset: {name!r}")]
    return []


def _description_present(ctx: Context) -> list[Issue]:
    if ctx.text is None:
        return []
    fm, _ = parse_skill(ctx.text)
    desc = fm.get("description")
    if desc is None or not str(desc).strip():
        return [Issue("description_present", "error", "`description` empty")]
    return []


def _companion_ref_scan(ctx: Context) -> list[Issue]:
    b = ctx.bundle
    if b is None:
        return []
    issues: list[Issue] = []
    text = f"---\n{b.frontmatter}\n---\n{b.body}" if b.frontmatter else b.body
    for relpath in b.companions:
        if relpath not in text:
            issues.append(Issue("companion_ref_scan", "warn", f"orphan: {relpath}"))
    # path-looking tokens with no matching companion file → broken ref
    for token in re.findall(r"(?<![\w./-])((?:[\w.-]+/)+[\w.-]+)", text):
        if token not in b.companions:
            issues.append(Issue("companion_ref_scan", "warn", f"broken ref: {token}"))
    # bare-filename candidates: companion basename used without its dir part
    for relpath in b.companions:
        basename = relpath.rsplit("/", 1)[-1]
        if "/" in relpath and re.search(rf"(?<![\w/]){re.escape(basename)}(?![\w])", text):
            issues.append(
                Issue("companion_ref_scan", "warn", f"bare-filename candidate: {basename}")
            )
    return issues


def _normalization(ctx: Context) -> list[Issue]:
    if ctx.text is None:
        return []
    if ctx.text != normalize_text(ctx.text):
        return [Issue("normalization", "error", "text not normalized (LF/BOM/trailing newline/`./`)")]
    return []


def _duplicate_names(ctx: Context) -> list[Issue]:
    if ctx.target_names is None:
        return []
    seen: dict[str, list[str]] = {}
    for name, target_id in ctx.target_names:
        seen.setdefault(name, []).append(target_id)
    return [
        Issue("duplicate_names", "warn", f"duplicate name {name!r}: ids {ids}")
        for name, ids in seen.items()
        if len(ids) > 1
    ]


def _cross_skill_mentions(ctx: Context) -> list[Issue]:
    old = ctx.renamed_from
    if not old or ctx.bundle is None:
        return []
    mentioned_in = [
        name
        for name, b in ctx.store_bundles.items()
        if name != ctx.bundle.name and old in (b.body + str(b.frontmatter))
    ]
    if mentioned_in:
        return [
            Issue(
                "cross_skill_mentions",
                "warn",
                f"{old!r} is referenced in: {', '.join(mentioned_in)}",
            )
        ]
    return []


def _store_integrity(ctx: Context) -> list[Issue]:
    if ctx.bundle is None or ctx.dir_name is None:
        return []
    # frontmatter name, not bundle.name (which may have been set to the dir name)
    fm_name = ctx.bundle.frontmatter.get("name")
    if ctx.dir_name != fm_name:
        return [
            Issue(
                "store_integrity",
                "error",
                f"dir name {ctx.dir_name!r} != frontmatter name {fm_name!r}",
            )
        ]
    return []


# (name, triggers, fn) — the registry. New checks are added here (meta-rule).
REGISTRY: list[tuple[str, frozenset[str], object]] = [
    ("frontmatter_valid", frozenset({POST_EDIT, IMPORT}), _frontmatter_valid),
    ("description_present", frozenset({POST_EDIT, IMPORT}), _description_present),
    ("companion_ref_scan", frozenset({POST_EDIT, IMPORT, SCAN}), _companion_ref_scan),
    ("normalization", frozenset({POST_EDIT, IMPORT, SCAN}), _normalization),
    ("duplicate_names", frozenset({SCAN}), _duplicate_names),
    ("cross_skill_mentions", frozenset({POST_EDIT, RENAME_DELETE}), _cross_skill_mentions),
    ("store_integrity", frozenset({POST_EDIT, IMPORT, SCAN}), _store_integrity),
]


def run_checks(trigger: str, ctx: Context) -> list[Issue]:
    """Run every check wired to `trigger`; return all issues."""
    issues: list[Issue] = []
    for _name, triggers, fn in REGISTRY:
        if trigger in triggers:
            issues.extend(fn(ctx))
    return issues
