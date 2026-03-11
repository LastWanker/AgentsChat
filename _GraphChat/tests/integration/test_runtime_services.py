from __future__ import annotations

from graphchat import GraphChatRuntime


class ForceDissolveProvider:
    def plan_action(self, _state: dict) -> dict:
        return {
            "action": "dissolve_group",
            "payload": {"text": "force dissolve", "world_scope": "group:main"},
        }


def test_runtime_approval_queue_resume_flow(tmp_path) -> None:
    runtime = GraphChatRuntime(
        base_dir=tmp_path / "data",
        agents=["agent_1"],
        checkpointer_backend="memory",
        model_provider=ForceDissolveProvider(),
    )
    outputs = runtime.submit_user_text(session_id="s_apr", text="请解散群")
    assert outputs == []

    pending = runtime.list_approval_requests(session_id="s_apr", status="pending")
    assert len(pending) == 1
    request_id = pending[0]["request_id"]

    resumed = runtime.resolve_approval(request_id=request_id, decision="approve", reviewer="tester")
    resumed_events = resumed.get("resumed_events", [])
    assert len(resumed_events) == 1
    assert resumed_events[0]["action_id"] == "dissolve_group"

    still_pending = runtime.list_approval_requests(session_id="s_apr", status="pending")
    assert still_pending == []
    runtime.close()


def test_runtime_agent_registry_disable_should_take_effect(tmp_path) -> None:
    runtime = GraphChatRuntime(
        base_dir=tmp_path / "data",
        agents=["agent_1", "agent_2"],
        checkpointer_backend="memory",
    )
    runtime.set_agent_enabled("agent_2", False)
    outputs = runtime.submit_user_text(session_id="s_lifecycle", text="hello")
    assert len(outputs) == 1
    assert outputs[0]["actor_id"] == "agent_1"
    runtime.close()


def test_runtime_stream_and_observability_snapshot(tmp_path) -> None:
    runtime = GraphChatRuntime(
        base_dir=tmp_path / "data",
        agents=["agent_1"],
        checkpointer_backend="memory",
    )
    chunks = list(runtime.stream_user_text(session_id="s_stream", text="hello"))
    assert any(item.get("type") == "node_update" for item in chunks)

    snapshot = runtime.get_observability_snapshot(session_id="s_stream")
    assert "checkpointers" in snapshot
    assert "agents" in snapshot
    assert snapshot.get("session_event_count", 0) >= 0
    runtime.close()
