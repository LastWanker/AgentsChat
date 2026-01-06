from events.intention_finalizer import IntentionFinalizer
from events.intention_schemas import IntentionDraft, RetrievalInstruction
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


def test_draft_needs_retrieval_plan(tmp_path):
    query = EventQuery(EventStore(base_dir=tmp_path, session_id="s", metadata={}))
    resolver = ReferenceResolver(query)
    finalizer = IntentionFinalizer(resolver)

    draft = IntentionDraft(kind="speak", message_plan="hi", retrieval_plan=[])
    draft.intention_id = "d1"

    try:
        finalizer.finalize(draft, agent_id="agent", intention_id="d1")
        assert False, "expected ValueError"
    except ValueError as exc:  # noqa: PT011
        assert "retrieval_plan" in str(exc)


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
        message_plan="带上 resolver 找到的引用回复",
        retrieval_plan=[
            RetrievalInstruction(name="search", keywords=["讨论"], event_types=["speak"], scope="public", limit=2)
        ],
        target_scope="public",
    )

    final_intention = finalizer.finalize(draft, agent_id="agent-1", intention_id="final-1")

    assert final_intention.payload["text"] == draft.message_plan
    assert {ref["event_id"] for ref in final_intention.references} == {"e-found"}
    # references 必须与 resolver 返回一致，不允许额外杜撰
    assert {ref["event_id"] for ref in final_intention.candidate_references} == {"e-found"}