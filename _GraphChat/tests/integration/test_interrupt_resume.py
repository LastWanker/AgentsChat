from __future__ import annotations

from langgraph.types import Command

from graphchat import GraphChatRuntime


class ForceDissolveProvider:
    def plan_action(self, _state: dict) -> dict:
        return {
            "action": "dissolve_group",
            "payload": {"text": "force dissolve", "world_scope": "group:main"},
        }


def test_interrupt_and_resume_should_emit_event(tmp_path) -> None:
    runtime = GraphChatRuntime(
        base_dir=tmp_path / "data",
        agents=["agent_1"],
        checkpointer_backend="memory",
        model_provider=ForceDissolveProvider(),
    )
    config = {"configurable": {"thread_id": "s_interrupt:agent:agent_1"}}
    state = {
        "session_id": "s_interrupt",
        "agent_id": "agent_1",
        "visible_events": [
            {"event_id": "e1", "payload": {"text": "x"}, "world_scope": "group:main"}
        ],
        "silent_rounds": 0,
        "max_silent_rounds": 1,
        "emitted_events": [],
        "errors": [],
    }

    first = runtime.agent_graph.invoke(state, config=config)
    assert "__interrupt__" in first

    resumed = runtime.agent_graph.invoke(Command(resume={"decision": "approve"}), config=config)
    emitted = resumed.get("emitted_events", [])
    assert len(emitted) == 1
    assert emitted[0]["action_id"] == "dissolve_group"
    runtime.close()

