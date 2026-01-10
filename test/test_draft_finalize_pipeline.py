from events.intention_finalizer import IntentionFinalizer
from events.intention_schemas import IntentionDraft
from events.query import EventQuery
from events.reference_resolver import ReferenceResolver
from events.store import EventStore
from events.types import Event


def _make_event(event_id: str, scope: str, text: str) -> Event:
    return Event(
        event_id=event_id,
        type="speak",
        timestamp="2024-01-01T00:00:00+00:00",
        sender="tester",
        scope=scope,
        content={"text": text},
    )


def test_finalizer_only_uses_resolver_results(tmp_path):
    store = EventStore(base_dir=tmp_path, session_id="sess", metadata={})
    store.append(_make_event("e-found", "public", "需要引用的讨论"))
    store.append(_make_event("e-ignore", "group:1", "其他范围"))

    query = EventQuery(store)
    resolver = ReferenceResolver(query)
    finalizer = IntentionFinalizer(resolver)

    draft = IntentionDraft(
        intention_id="draft-1",
        agent_id="agent-1",
        kind="speak",
        draft_text="带上 resolver 找到的引用回复",
        retrieval_tags=[],
        retrieval_keywords=["讨论"],
        target_scope="public",
        agent_count=1,
    )

    final_intention = finalizer.finalize(draft, agent_id="agent-1", intention_id="final-1")

    assert final_intention.payload["text"] == draft.draft_text
    assert {ref["event_id"] for ref in final_intention.references} == {"e-found"}
