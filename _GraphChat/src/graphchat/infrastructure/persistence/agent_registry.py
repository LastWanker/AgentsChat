from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AgentRegistry:
    def __init__(self, path: Path, bootstrap_agents: list[str] | None = None):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            records = []
            for agent_id in bootstrap_agents or []:
                records.append(
                    {
                        "agent_id": str(agent_id),
                        "enabled": True,
                        "role": "member",
                        "permissions": [],
                        "updated_at": _utc_now(),
                    }
                )
            self._write({"agents": records})

    def _read(self) -> dict:
        if not self._path.exists():
            return {"agents": []}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {"agents": []}
        if not isinstance(payload, dict):
            return {"agents": []}
        return payload

    def _write(self, payload: dict) -> None:
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_agents(self, *, include_disabled: bool = True) -> list[dict]:
        items = list(self._read().get("agents", []))
        if include_disabled:
            return items
        return [item for item in items if bool(item.get("enabled", True))]

    def get_agent(self, agent_id: str) -> dict | None:
        for item in self.list_agents(include_disabled=True):
            if item.get("agent_id") == agent_id:
                return item
        return None

    def enabled_agent_ids(self) -> list[str]:
        return [str(item.get("agent_id")) for item in self.list_agents(include_disabled=False)]

    def upsert_agent(
        self,
        *,
        agent_id: str,
        enabled: bool = True,
        role: str = "member",
        permissions: list[str] | None = None,
    ) -> dict:
        data = self._read()
        items = list(data.get("agents", []))
        updated = {
            "agent_id": str(agent_id),
            "enabled": bool(enabled),
            "role": str(role),
            "permissions": list(permissions or []),
            "updated_at": _utc_now(),
        }
        for idx, old in enumerate(items):
            if old.get("agent_id") == agent_id:
                items[idx] = {**old, **updated}
                data["agents"] = items
                self._write(data)
                return items[idx]
        items.append(updated)
        data["agents"] = items
        self._write(data)
        return updated

    def set_enabled(self, agent_id: str, enabled: bool) -> dict | None:
        item = self.get_agent(agent_id)
        if item is None:
            return None
        return self.upsert_agent(
            agent_id=agent_id,
            enabled=enabled,
            role=str(item.get("role", "member")),
            permissions=list(item.get("permissions", [])),
        )

