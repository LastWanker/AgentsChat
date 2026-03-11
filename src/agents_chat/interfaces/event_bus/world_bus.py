from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Optional


class WorldBus:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._by_id: dict[str, dict[str, Any]] = {}
        self.observers: list[Any] = []

    def add_observer(self, observer: Any) -> None:
        self.observers.append(observer)

    def emit(self, event: Any) -> None:
        event_dict = self._to_dict(event)
        self.events.append(event_dict)
        if event_id := event_dict.get("event_id"):
            self._by_id[event_id] = event_dict
        for observer in self.observers:
            observer.on_event(event_dict)

    def get_event(self, event_id: str) -> Optional[dict[str, Any]]:
        return self._by_id.get(event_id)

    @staticmethod
    def _to_dict(event: Any) -> dict[str, Any]:
        if is_dataclass(event):
            return asdict(event)
        if isinstance(event, dict):
            return event
        return getattr(event, "__dict__", {}) or {}

