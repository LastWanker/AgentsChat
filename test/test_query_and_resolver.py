from events.intention_schemas import IntentionDraft, RetrievalInstruction
from events.query import EventQuery
from events.reference_resolver import ReferenceResolver
from events.store import EventStore
from events.types import Event


def _make_event(
    *,
    event_id: str,
    type: str,
    timestamp: str,
    scope: str,
    sender: str = "tester",
    content: dict | None = None,
    references=None,
) -> Event:
    return Event(
        event_id=event_id,
        type=type,
        timestamp=timestamp,
        sender=sender,
        scope=scope,
        content=content or {},
        references=references or [],
    )


def _bootstrap_store(tmp_path) -> EventStore:
    store = EventStore(base_dir=tmp_path, session_id="sess", metadata={})
    base_events = [
        _make_event(
            event_id="e1",
            type="speak",
            timestamp="2024-01-01T00:00:00+00:00",
            scope="public",
            content={"text": "第一次讨论"},
        ),
        _make_event(
            event_id="e2",
            type="decision",
            timestamp="2024-01-02T00:00:00+00:00",
            scope="public",
            content={"text": "行动计划"},
            references=[{"event_id": "e1"}],
        ),
        _make_event(
            event_id="e3",
            type="note",
            timestamp="2024-01-03T00:00:00+00:00",
            scope="group:1",
            content={"text": "组内记录"},
        ),
        _make_event(
            event_id="e4",
            type="speak",
            timestamp="2024-01-04T00:00:00+00:00",
            scope="public",
            content={"text": "跟进决策"},
            references=[{"event_id": "e2"}],
        ),
    ]
    for ev in base_events:
        store.append(ev)
    return store


def test_recent_orders_by_time_and_scope(tmp_path):
    store = _bootstrap_store(tmp_path)
    query = EventQuery(store)

    recent = query.recent("public", n=2)

    assert [ev.event_id for ev in recent] == ["e4", "e2"]


def test_search_filters_keywords_type_and_time(tmp_path):
    store = _bootstrap_store(tmp_path)
    query = EventQuery(store)

    results = query.search(
        scope="public",
        keywords=["计划"],
        limit=5,
        event_types=["decision"],
        after_time="2024-01-01T12:00:00+00:00",
    )

    assert [ev.event_id for ev in results] == ["e2"]


def test_thread_up_traverses_ancestors(tmp_path):
    store = _bootstrap_store(tmp_path)
    query = EventQuery(store)

    ancestors = query.thread_up("e4", depth=2)

    assert [ev.event_id for ev in ancestors] == ["e2", "e1"]


def test_reference_resolver_builds_candidates(tmp_path):
    store = _bootstrap_store(tmp_path)
    query = EventQuery(store)
    resolver = ReferenceResolver(query)

    draft = IntentionDraft(
        kind="speak",
        message_plan="回应讨论",
        retrieval_plan=[
            RetrievalInstruction(
                name="search-discussion",
                keywords=["讨论"],
                event_types=["speak"],
                scope="public",
                limit=1,
            ),
            RetrievalInstruction(
                name="thread",
                after_event_id="e4",
                thread_depth=1,
            ),
        ],
        target_scope="public",
    )

    references = resolver.resolve(draft)

    assert {ref["event_id"] for ref in references} == {"e1", "e2"}