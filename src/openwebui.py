"""OpenWebUI adapter — HTTP target (official /v1/skills API).

Spec: API key intentionally created in OWUI; create via POST (409 → find id);
delete via DELETE /v1/skills/{id}; status via GET /v1/skills/{id}/status.
files content: text, base64 fallback for binary.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request

from .adapter import Adapter
from .name import normalize_name


class OWUIError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"OWUI {status}: {detail}")


def _b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def _decode(content: str) -> bytes:
    """OWUI file content: we always write base64, so try base64 first;
    non-b64 text (e.g. created by other clients) falls back to raw UTF-8."""
    try:
        return base64.b64decode(content, validate=True)
    except Exception:
        return str(content).encode("utf-8")


class OpenWebUIAdapter(Adapter):
    id = "openwebui"

    def __init__(self, base_url: str, api_key: str):
        base = base_url.rstrip("/")
        if not base.startswith(("http://", "https://")):
            base = "http://" + base
        self.base = base
        self.key = api_key

    def _req(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=data,
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(req) as resp:
                body = resp.read().decode()
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            raise OWUIError(e.code, detail) from e
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise OWUIError(0, f"non-JSON response: {body[:120]!r}") from None

    # --- list / read ------------------------------------------------------

    def list_skills(self) -> dict[str, str]:
        r = self._req("GET", "/v1/skills")
        return {normalize_name(s["name"]): s["id"] for s in r.get("data", [])}

    def read_skill(self, target_id: str) -> tuple[bytes, dict[str, bytes], dict[str, int]]:
        r = self._req("GET", f"/v1/skills/{target_id}")
        d = r["data"]
        text = d["content"].encode("utf-8")
        companions = {f["path"]: _decode(f["content"]) for f in d.get("files", [])}
        return text, companions, {}

    # --- write / delete / create -------------------------------------------

    def write_skill(self, target_id: str, text: str, companions: dict[str, bytes]) -> None:
        files = [{"path": p, "content": base64.b64encode(data).decode()} for p, data in companions.items()]
        self._req("PUT", f"/v1/skills/{target_id}", {"content": text, "files": files})

    def delete_skill(self, target_id: str) -> None:
        self._req("DELETE", f"/v1/skills/{target_id}")

    def create_skill(self, name: str) -> str:
        name = normalize_name(name)
        try:
            r = self._req("POST", "/v1/skills", {"name": name, "description": "", "content": "", "files": []})
            return r["data"]["id"]
        except OWUIError as e:
            if e.status == 409:  # already exists → find its id
                for n, tid in self.list_skills().items():
                    if n == name:
                        return tid
            raise

    # --- status (for the status command) -----------------------------------

    def status(self, target_id: str) -> str:
        r = self._req("GET", f"/v1/skills/{target_id}/status")
        return r["data"].get("status", "unknown")
