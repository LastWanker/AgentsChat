from __future__ import annotations

from typing import Any

from events.session_memory import SessionMemory
from events.types import Event, normalize_event_dict


class SessionMaintenanceObserver:
    def __init__(self, *, memory: SessionMemory, store: Any):
        self.memory = memory
        self.store = store
        self.id = "session_maintenance"

    def on_event(self, event: dict) -> None:
        if isinstance(event, Event):
            ev = event
        else:
            try:
                ev = Event(**normalize_event_dict(event))
            except Exception:
                return
        self.memory.handle_event(ev, self.store)
