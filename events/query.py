from typing import List, Optional
from .store import EventStore
from .types import Event

class EventQuery:
    def __init__(self, store: EventStore):
        self.store = store

    def by_id(self, event_id: str) -> Optional[Event]:
        return self.store.get(event_id)

    def last_n(self, n: int = 20) -> List[Event]:
        evs = self.store.all()
        return evs[-n:]
