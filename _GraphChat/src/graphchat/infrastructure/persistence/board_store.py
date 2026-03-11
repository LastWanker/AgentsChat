from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class BoardStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _board_path(self, session_id: str) -> Path:
        session_dir = self.base_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir / "board.json"

    def _read_items(self, session_id: str) -> list[dict]:
        path = self._board_path(session_id)
        if not path.exists():
            return []
        return list(json.loads(path.read_text(encoding="utf-8")))

    def _write_items(self, session_id: str, items: list[dict]) -> None:
        path = self._board_path(session_id)
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def list_items(
        self,
        session_id: str,
        *,
        include_archived: bool = True,
        include_deleted: bool = False,
    ) -> list[dict]:
        items = self._read_items(session_id)
        out: list[dict] = []
        for item in items:
            if not include_deleted and bool(item.get("deleted", False)):
                continue
            if not include_archived and bool(item.get("archived", False)):
                continue
            out.append(item)
        return out

    def get_item(self, session_id: str, item_id: str) -> dict | None:
        for item in self._read_items(session_id):
            if item.get("item_id") == item_id:
                return item
        return None

    def upsert_item(self, item: dict) -> None:
        session_id = item["session_id"]
        items = self._read_items(session_id)
        merged = dict(item)
        merged["updated_at"] = self._now()
        found = False
        for i, old in enumerate(items):
            if old.get("item_id") == item.get("item_id"):
                items[i] = {**old, **merged}
                found = True
                break
        if not found:
            items.append(merged)
        self._write_items(session_id, items)

    def update_item_fields(self, session_id: str, item_id: str, patch: dict) -> bool:
        items = self._read_items(session_id)
        for idx, item in enumerate(items):
            if item.get("item_id") != item_id:
                continue
            items[idx] = {**item, **patch, "updated_at": self._now()}
            self._write_items(session_id, items)
            return True
        return False

    def archive_item(self, session_id: str, item_id: str, archived: bool = True) -> bool:
        return self.update_item_fields(session_id, item_id, {"archived": bool(archived)})

    def delete_item(self, session_id: str, item_id: str, *, hard: bool = False) -> bool:
        items = self._read_items(session_id)
        for idx, item in enumerate(items):
            if item.get("item_id") != item_id:
                continue
            if hard:
                items.pop(idx)
            else:
                items[idx] = {**item, "deleted": True, "updated_at": self._now()}
            self._write_items(session_id, items)
            return True
        return False

    def gc_items(self, session_id: str) -> int:
        items = self._read_items(session_id)
        kept = [item for item in items if not bool(item.get("deleted", False))]
        removed = len(items) - len(kept)
        if removed > 0:
            self._write_items(session_id, kept)
        return removed
