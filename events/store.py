from typing import Dict, List, Optional
from .types import Event

class EventStore:
    def __init__(self):
        self._events: List[Event] = []
        self._by_id: Dict[str, Event] = {}

    def append(self, event: Event) -> None:
        self._events.append(event)
        self._by_id[event.event_id] = event
        print(
            f"[events/store.py] 🗃️ 收纳事件 {event.event_id}，类型 {event.type}，目前库存 {len(self._events)} 条。"
        )

    def get(self, event_id: str) -> Optional[Event]:
        return self._by_id.get(event_id)

    def all(self) -> List[Event]:
        return list(self._events)
