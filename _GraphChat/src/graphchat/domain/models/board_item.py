from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class BoardItem:
    session_id: str
    scope: str
    title: str
    status: str = "todo"
    priority: str = "medium"
    due_at: str | None = None
    archived: bool = False
    deleted: bool = False
    owner_id: str | None = None
    linked_event_id: str | None = None
    item_id: str = field(default_factory=lambda: f"b_{uuid4().hex[:10]}")
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "session_id": self.session_id,
            "scope": self.scope,
            "title": self.title,
            "status": self.status,
            "priority": self.priority,
            "due_at": self.due_at,
            "archived": self.archived,
            "deleted": self.deleted,
            "owner_id": self.owner_id,
            "linked_event_id": self.linked_event_id,
            "updated_at": self.updated_at,
        }
