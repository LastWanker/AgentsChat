from __future__ import annotations

from graphchat import GraphChatRuntime


def test_world_agent_pipeline_emits_events(tmp_path) -> None:
    runtime = GraphChatRuntime(
        base_dir=tmp_path / "data",
        agents=["agent_1", "agent_2"],
        checkpointer_backend="memory",
    )
    outputs = runtime.submit_user_text(session_id="s_state", text="hello world")
    assert len(outputs) == 2
    assert all(item.get("event_id") for item in outputs)
    runtime.close()


def test_invalid_incoming_scope_rejected(tmp_path) -> None:
    runtime = GraphChatRuntime(
        base_dir=tmp_path / "data",
        agents=["agent_1"],
        checkpointer_backend="memory",
    )

    bad_event = {
        "event_id": "e_bad",
        "session_id": "s_scope",
        "world_scope": "invalid_scope",
        "actor_id": "user",
        "action_id": "speak",
        "action_version": "1.0.0",
        "payload": {"text": "bad"},
        "references": [],
        "focus_reference": None,
        "created_at": "2026-03-11T00:00:00Z",
        "trace": {},
    }

    result = runtime.world_graph.invoke(
        {
            "session_id": "s_scope",
            "tick": 0,
            "incoming_events": [bad_event],
            "pending_events": [],
            "agents": ["agent_1"],
            "agent_outputs": [],
            "published_events": [],
            "errors": [],
        },
        config={"configurable": {"thread_id": "s_scope:world"}},
    )
    assert any("invalid world_scope" in err for err in result.get("errors", []))
    assert all(event.get("event_id") != "e_bad" for event in result.get("pending_events", []))
    assert all(event.get("event_id") != "e_bad" for event in result.get("routed_events", []))
    runtime.close()
