"""OpenWebUI adapter — HTTP target.

Real API (verified via /openapi.json on the live instance):
- GET    /api/v1/skills/                 → [SkillUserResponse]
- POST   /api/v1/skills/create           → body SkillForm (id required, client-chosen)
- GET    /api/v1/skills/id/{id}
- POST   /api/v1/skills/id/{id}/update   → body SkillForm (POST, not PUT)
- DELETE /api/v1/skills/id/{id}/delete   → bool

No companion files in this API — skills are a single `content` string.
Companions ride inline as `<!-- file:<rel> -->…<!-- /file -->` markers
(spec E): small → inline (base64 for binary), large → external-ref guide.
"""

from __future__ import annotations

import base64
import json
import re
import socket
import urllib.error
import urllib.request
from pathlib import Path

from .adapter import Adapter
from .canonical import parse_skill
from .name import normalize_name

# --- inline flatten (spec E) -------------------------------------------------
# Companions ride inside the OWUI content as structural markers:
#   <!-- file:<relpath> [encoding:base64] [ref:external] -->
#   <content>
#   <!-- /file -->
# Markers are appended at the end of the md and re-parsed on read (lossless).

_MARKER = re.compile(
    r"<!-- file:([^\s>]+)([^>]*) -->\n(.*?)\n<!-- /file -->\n?", re.S
)


def _flatten(text: str, companions: dict[str, bytes], threshold: int, store_path: Path | None, hostname: str | None = None) -> str:
    parts = [text.rstrip("\n")]
    for rel in sorted(companions):
        data = companions[rel]
        if len(data) <= threshold:
            try:
                body = data.decode("utf-8")
                parts.append(f"<!-- file:{rel} -->\n{body}\n<!-- /file -->")
            except UnicodeDecodeError:
                parts.append(
                    f"<!-- file:{rel} encoding:base64 -->\n{base64.b64encode(data).decode()}\n<!-- /file -->"
                )
        else:
            host = hostname or socket.gethostname()
            loc = f"{store_path / rel}" if store_path else "<store>"
            parts.append(
                f"<!-- file:{rel} ref:external -->\n"
                f"This companion is too large to inline. It lives in the skill-sync store on `{host}`:\n"
                f"  {loc}\n"
                f"Open a terminal there (e.g. `open -R {loc}`).\n"
                f"<!-- /file -->"
            )
    return "\n\n".join(parts) + "\n"


def _unflatten(text: str) -> tuple[str, dict[str, bytes]]:
    comps: dict[str, bytes] = {}

    def repl(m):
        rel, attrs, body = m.group(1), m.group(2), m.group(3)
        encoding = "base64" if "encoding:base64" in attrs else None
        comps[rel] = base64.b64decode(body) if encoding else body.encode("utf-8")
        return ""

    out = _MARKER.sub(repl, text).rstrip("\n") + "\n"
    return out, comps


class OWUIError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"OWUI {status}: {detail}")


class OpenWebUIAdapter(Adapter):
    id = "openwebui"

    def __init__(self, base_url: str, api_key: str, inline_max_bytes: int = 65536, store_path: Path | None = None, hostname: str | None = None):
        base = base_url.rstrip("/")
        if not base.startswith(("http://", "https://")):
            base = "http://" + base
        self.base = base
        self.key = api_key
        self.inline_max_bytes = inline_max_bytes
        self.store_path = store_path
        self.hostname = hostname

    def _req(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=data,
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode()
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            raise OWUIError(e.code, detail) from e
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise OWUIError(0, f"non-JSON response: {raw[:120]!r}") from None

    # --- list / read ------------------------------------------------------

    def list_skills(self) -> dict[str, str]:
        return {s["name"]: s["id"] for s in self.list_skills_full()}

    def list_skills_full(self) -> list[dict]:
        r = self._req("GET", "/api/v1/skills/")
        return [
            {
                "name": normalize_name(s["name"]),
                "id": s["id"],
                "is_active": bool(s.get("is_active", True)),
            }
            for s in r
        ]

    def rename_on_target(self, old_id: str, new_name: str) -> str | None:
        """id is client-chosen → rename = recreate (POST /create + DELETE /old)."""
        self.create_skill(new_name)
        self.delete_skill(old_id)
        return new_name

    def read_skill(self, target_id: str) -> tuple[bytes, dict[str, bytes], dict[str, int]]:
        d = self._req("GET", f"/api/v1/skills/id/{target_id}")
        text, companions = _unflatten(d["content"])
        return text.encode("utf-8"), companions, {}

    # --- write / delete / create -------------------------------------------

    def write_skill(self, target_id: str, text: str, companions: dict[str, bytes]) -> None:
        if isinstance(text, bytes):
            text = text.decode("utf-8")
        fm, _ = parse_skill(text)
        name = fm.get("name") or target_id
        body = {
            "id": target_id,
            "name": name,
            "content": text,
            "meta": {"tags": []},
            "is_active": True,
        }
        if fm.get("description"):
            body["description"] = str(fm["description"])
        body["content"] = _flatten(
            text, companions, self.inline_max_bytes, self.store_path, self.hostname
        )
        self._req("POST", f"/api/v1/skills/id/{target_id}/update", body)

    def delete_skill(self, target_id: str) -> None:
        self._req("DELETE", f"/api/v1/skills/id/{target_id}/delete")

    def create_skill(self, name: str) -> str:
        name = normalize_name(name)
        self._req(
            "POST",
            "/api/v1/skills/create",
            {"id": name, "name": name, "content": "", "meta": {"tags": []}, "is_active": True},
        )
        return name
