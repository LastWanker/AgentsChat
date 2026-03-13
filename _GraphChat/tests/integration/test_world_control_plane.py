from __future__ import annotations

from graphchat import GraphChatRuntime


def test_world_command_create_agent_and_group_should_take_effect(tmp_path) -> None:
    runtime = GraphChatRuntime(
        base_dir=tmp_path / "data",
        agents=["agent_1"],
        checkpointer_backend="memory",
    )
    result_create = runtime.submit_world_command(
        session_id="s_world_cmd",
        command={
            "type": "create_agent",
            "payload": {"agent_id": "agent_9", "enabled": True, "join_main_group": True},
        },
        created_by="boss",
    )
    assert "agent_9" in runtime.agents
    assert any(item.get("action_id") == "world_command_applied" for item in result_create.get("published_events", []))

    runtime.submit_world_command(
        session_id="s_world_cmd",
        command={
            "type": "upsert_group",
            "payload": {"group_id": "team_alpha", "members": ["agent_9"]},
        },
        created_by="boss",
    )
    assert runtime.group_registry.members("team_alpha") == {"agent_9"}
    runtime.close()


def test_world_direct_chat_command_should_emit_direct_reply(tmp_path) -> None:
    runtime = GraphChatRuntime(
        base_dir=tmp_path / "data",
        agents=["agent_1"],
        checkpointer_backend="memory",
    )
    result = runtime.submit_world_command(
        session_id="s_direct_cmd",
        command={
            "type": "direct_chat",
            "payload": {"agent_id": "agent_1", "text": "status?"},
        },
        created_by="boss",
    )
    action_ids = [item.get("action_id") for item in result.get("published_events", [])]
    assert "direct_reply" in action_ids
    assert "world_command_applied" in action_ids
    runtime.close()

