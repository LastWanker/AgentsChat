from typing import List, Optional
from .references import ref_event_id
from .store import EventStore
from .types import Event, Reference

class EventQuery:
    def __init__(self, store: EventStore):
        self.store = store

    def by_id(self, ref_or_id: Reference | str) -> Optional[Event]:
        return self.store.get(ref_event_id(ref_or_id))

    def last_n(self, n: int = 20) -> List[Event]:
        evs = self.store.all()
        return evs[-n:]
