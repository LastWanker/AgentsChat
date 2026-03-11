from __future__ import annotations

_EVENT_ID_COUNTER = 1


def next_event_id() -> str:
    """Return the next incremental event id for the current session."""

    global _EVENT_ID_COUNTER
    event_id = _EVENT_ID_COUNTER
    _EVENT_ID_COUNTER += 1
    return str(event_id)


def sync_event_id_counter(next_id: int) -> None:
    """Ensure the event id counter is at least the given next id."""

    global _EVENT_ID_COUNTER
    if next_id <= 0:
        return
    if next_id > _EVENT_ID_COUNTER:
        _EVENT_ID_COUNTER = next_id