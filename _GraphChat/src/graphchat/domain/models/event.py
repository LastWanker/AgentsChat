from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class Event:
    session_id: str
    world_scope: str
    actor_id: str
    action_id: str
    action_version: str
    payload: dict
    references: list[dict] = field(default_factory=list)
    focus_reference: str | None = None
    trace: dict = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"e_{uuid4().hex[:12]}")
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "world_scope": self.world_scope,
            "actor_id": self.actor_id,
            "action_id": self.action_id,
            "action_version": self.action_version,
            "payload": self.payload,
            "references": self.references,
            "focus_reference": self.focus_reference,
            "created_at": self.created_at,
            "trace": self.trace,
        }

