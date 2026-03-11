from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ApprovalQueueStore:
    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write({"requests": []})

    def _read(self) -> dict:
        if not self._path.exists():
            return {"requests": []}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {"requests": []}
        if not isinstance(payload, dict):
            return {"requests": []}
        return payload

    def _write(self, payload: dict) -> None:
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def enqueue(
        self,
        *,
        session_id: str,
        agent_id: str,
        thread_id: str,
        interrupt_payload: dict,
    ) -> dict:
        data = self._read()
        requests = list(data.get("requests", []))
        for item in requests:
            if item.get("thread_id") == thread_id and item.get("status") == "pending":
                return item
        request = {
            "request_id": f"apr_{uuid4().hex[:12]}",
            "session_id": session_id,
            "agent_id": agent_id,
            "thread_id": thread_id,
            "status": "pending",
            "interrupt_payload": dict(interrupt_payload),
            "decision": None,
            "reviewer": None,
            "note": None,
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }
        requests.append(request)
        data["requests"] = requests
        self._write(data)
        return request

    def list_requests(self, *, status: str | None = None, session_id: str | None = None) -> list[dict]:
        items = list(self._read().get("requests", []))
        if status is not None:
            items = [item for item in items if str(item.get("status")) == status]
        if session_id is not None:
            items = [item for item in items if str(item.get("session_id")) == session_id]
        return items

    def get_request(self, request_id: str) -> dict | None:
        for item in self.list_requests():
            if item.get("request_id") == request_id:
                return item
        return None

    def resolve(
        self,
        *,
        request_id: str,
        decision: str,
        reviewer: str | None = None,
        note: str | None = None,
    ) -> dict | None:
        data = self._read()
        items = list(data.get("requests", []))
        for idx, item in enumerate(items):
            if item.get("request_id") != request_id:
                continue
            updated = {
                **item,
                "status": "resolved",
                "decision": decision,
                "reviewer": reviewer,
                "note": note,
                "updated_at": _utc_now(),
            }
            items[idx] = updated
            data["requests"] = items
            self._write(data)
            return updated
        return None
