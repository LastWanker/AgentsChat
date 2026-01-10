from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Sequence

from .references import ref_event_id
from .store import EventStore
from .types import Event, Reference


class EventQuery:
    def __init__(self, store: EventStore):
        self.store = store

    def by_id(self, ref_or_id: Reference | str) -> Optional[Event]:
        return self.store.get(ref_event_id(ref_or_id))

    def last_n(self, n: int = 6) -> List[Event]:
        evs = self.store.all()
        return evs[-n:]

    # --- resolver-friendly helpers ---
    def recent(self, scope: str, n: int = 6) -> List[Event]:
        """Return the most recent events in a scope."""

        scoped_events = [ev for ev in self.store.all() if ev.scope == scope]
        return self._sort_by_time(scoped_events)[:n]

    def search(
            self,
            *,
            scope: str,
            keywords: Sequence[str],
            limit: Optional[int] = None,
            event_types: Optional[Sequence[str]] = None,
            after_time: Optional[str] = None,
    ) -> List[Event]:
        """Naive keyword search with optional type and time filters."""

        needles = [k.lower() for k in keywords if k]
        after_dt = self._parse_time(after_time) if after_time else None

        def matches(ev: Event) -> bool:
            if ev.scope != scope:
                return False
            if event_types and ev.type not in event_types:
                return False
            ev_dt = self._parse_time(ev.timestamp)
            if after_dt and (ev_dt is None or ev_dt <= after_dt):
                return False
            if not needles:
                return True
            haystack = f"{ev.content} {ev.metadata}".lower()
            return any(needle in haystack for needle in needles)

        filtered = [ev for ev in self.store.all() if matches(ev)]
        sorted_events = self._sort_by_time(filtered)
        if limit is None:
            return sorted_events
        return sorted_events[:limit]

    def thread_up(self, event_id: str, depth: int) -> List[Event]:
        """Follow reference chains upwards for a limited depth."""

        collected: List[Event] = []
        frontier = [event_id]
        seen = set(frontier)

        for _ in range(depth):
            next_frontier: list[str] = []
            for current_id in frontier:
                event = self.by_id(current_id)
                if not event:
                    continue
                for ref in event.references:
                    ancestor_id = ref_event_id(ref)
                    if ancestor_id in seen:
                        continue
                    ancestor_event = self.by_id(ancestor_id)
                    if ancestor_event:
                        collected.append(ancestor_event)
                        next_frontier.append(ancestor_id)
                        seen.add(ancestor_id)
            if not next_frontier:
                break
            frontier = next_frontier

        return self._sort_by_time(collected)

    # --- helpers ---
    @staticmethod
    def _parse_time(ts: Optional[str]) -> Optional[datetime]:
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts)
        except Exception:
            return None

    def _sort_by_time(self, events: List[Event]) -> List[Event]:
        return sorted(
            events,
            key=lambda ev: self._parse_time(ev.timestamp) or datetime.min,
            reverse=True,
        )
