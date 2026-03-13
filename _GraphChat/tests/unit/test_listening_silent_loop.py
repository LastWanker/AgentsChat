from __future__ import annotations

from graphchat.application.graphs.subgraphs.listening_subgraph import build_listening_subgraph


def test_listening_subgraph_should_reduce_ttl_and_decide_wake() -> None:
    graph = build_listening_subgraph()
    state = {
        "agent_id": "agent_1",
        "visible_events": [{"event_id": "e1", "payload": {"text": "hello @agent_1"}}],
        "global_ttl": 5,
        "silent_rounds": 0,
        "max_silent_rounds": 3,
    }
    result = graph.invoke(state)
    assert result.get("last_event", {}).get("event_id") == "e1"
    assert result.get("global_ttl") == 4
    assert result.get("should_wake") is True
