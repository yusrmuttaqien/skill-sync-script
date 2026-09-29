"""OpenWebUI adapter — HTTP target.

Real API (verified via /openapi.json on the live instance):
- GET    /api/v1/skills/                 → [SkillUserResponse]
- POST   /api/v1/skills/create           → body SkillForm (id required, client-chosen)
- GET    /api/v1/skills/id/{id}
- POST   /api/v1/skills/id/{id}/update   → body SkillForm (POST, not PUT)
- DELETE /api/v1/skills/id/{id}/delete   → bool

No companion files in this API — skills are a single `content` string.
Companions on export are NOT sent (inline-flatten is the deferred bridge).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .adapter import Adapter
from .canonical import parse_skill
from .name import normalize_name


class OWUIError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"OWUI {status}: {detail}")


class OpenWebUIAdapter(Adapter):
    id = "openwebui"

    def __init__(self, base_url: str, api_key: str):
        base = base_url.rstrip("/")
        if not base.startswith(("http://", "https://")):
            base = "http://" + base
        self.base = base
        self.key = api_key

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
        r = self._req("GET", "/api/v1/skills/")
        return {normalize_name(s["name"]): s["id"] for s in r}

    def read_skill(self, target_id: str) -> tuple[bytes, dict[str, bytes], dict[str, int]]:
        d = self._req("GET", f"/api/v1/skills/id/{target_id}")
        return d["content"].encode("utf-8"), {}, {}

    # --- write / delete / create -------------------------------------------

    def write_skill(self, target_id: str, text: str, companions: dict[str, bytes]) -> None:
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
