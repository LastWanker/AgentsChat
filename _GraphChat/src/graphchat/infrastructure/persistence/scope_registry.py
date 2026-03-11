from __future__ import annotations

import json
from pathlib import Path


def _read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    if not isinstance(payload, dict):
        return default
    return payload


class GroupRegistry:
    def __init__(self, path: Path, bootstrap_agents: list[str] | None = None):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write({"groups": {"main": sorted(set(bootstrap_agents or []))}})

    def _read(self) -> dict:
        return _read_json(self._path, {"groups": {"main": []}})

    def _write(self, payload: dict) -> None:
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def members(self, group_id: str) -> set[str]:
        data = self._read()
        groups = data.get("groups", {})
        members = groups.get(group_id, [])
        return {str(agent_id) for agent_id in members if str(agent_id).strip()}

    def set_members(self, group_id: str, members: list[str]) -> None:
        data = self._read()
        groups = data.setdefault("groups", {})
        groups[group_id] = sorted({str(agent_id) for agent_id in members if str(agent_id).strip()})
        self._write(data)

    def add_member(self, group_id: str, agent_id: str) -> None:
        members = self.members(group_id)
        members.add(agent_id)
        self.set_members(group_id, sorted(members))

    def remove_member(self, group_id: str, agent_id: str) -> None:
        members = self.members(group_id)
        members.discard(agent_id)
        self.set_members(group_id, sorted(members))

    def groups_for_agent(self, agent_id: str) -> set[str]:
        data = self._read()
        out: set[str] = set()
        for group_id, members in data.get("groups", {}).items():
            if str(agent_id) in {str(x) for x in members}:
                out.add(str(group_id))
        return out


class DmRegistry:
    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write({"pairs": []})

    def _read(self) -> dict:
        return _read_json(self._path, {"pairs": []})

    def _write(self, payload: dict) -> None:
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _norm_pair(self, a: str, b: str) -> tuple[str, str]:
        x, y = str(a).strip(), str(b).strip()
        return (x, y) if x <= y else (y, x)

    def register_pair(self, a: str, b: str) -> None:
        pair = self._norm_pair(a, b)
        data = self._read()
        pairs = {tuple(item) for item in data.get("pairs", []) if isinstance(item, list) and len(item) == 2}
        pairs.add(pair)
        data["pairs"] = [list(item) for item in sorted(pairs)]
        self._write(data)

    def revoke_pair(self, a: str, b: str) -> None:
        pair = self._norm_pair(a, b)
        data = self._read()
        pairs = {tuple(item) for item in data.get("pairs", []) if isinstance(item, list) and len(item) == 2}
        pairs.discard(pair)
        data["pairs"] = [list(item) for item in sorted(pairs)]
        self._write(data)

    def is_allowed(self, a: str, b: str) -> bool:
        pair = self._norm_pair(a, b)
        data = self._read()
        pairs = {tuple(item) for item in data.get("pairs", []) if isinstance(item, list) and len(item) == 2}
        return pair in pairs

