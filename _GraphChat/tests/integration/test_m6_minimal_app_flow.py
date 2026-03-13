from __future__ import annotations

from graphchat import GraphChatRuntime


def test_m6_minimal_app_flow_should_support_group_discuss_rag_and_direct_chat(tmp_path) -> None:
    runtime = GraphChatRuntime(
        base_dir=tmp_path / "data",
        agents=["agent_1", "agent_2", "agent_3"],
        checkpointer_backend="memory",
    )
    session_id = "s_m6"

    runtime.submit_world_command(
        session_id=session_id,
        command={"type": "create_agent", "payload": {"agent_id": "agent_4", "enabled": True}},
        created_by="boss",
    )
    runtime.submit_world_commands(
        session_id=session_id,
        commands=[
            {"type": "upsert_group", "payload": {"group_id": "team_1", "members": ["agent_1", "agent_2"]}},
            {"type": "upsert_group", "payload": {"group_id": "team_2", "members": ["agent_3", "agent_4"]}},
        ],
        created_by="boss",
    )

    team1_outputs = runtime.submit_user_text(session_id=session_id, world_scope="group:team_1", text="team_1 同步")
    team1_actors = {item.get("actor_id") for item in team1_outputs}
    assert team1_actors == {"agent_1", "agent_2"}

    runtime.submit_world_commands(
        session_id=session_id,
        commands=[
            {
                "type": "set_agent_retrieval",
                "payload": {"agent_id": "agent_1", "channels": ["web_search", "world_history"]},
            },
            {
                "type": "set_agent_retrieval",
                "payload": {"agent_id": "agent_2", "channels": ["file_search"]},
            },
        ],
        created_by="boss",
    )
    rag_outputs = runtime.submit_user_text(session_id=session_id, world_scope="group:team_1", text="请查一下资料")
    rag_by_actor = {item.get("actor_id"): item for item in rag_outputs}
    assert rag_by_actor["agent_1"]["trace"].get("retrieval_channel") == "web_search"
    assert rag_by_actor["agent_2"]["trace"].get("retrieval_channel") == "world_history"

    discuss = runtime.submit_world_command(
        session_id=session_id,
        command={
            "type": "inject_task",
            "scope": "group:team_2",
            "payload": {"text": "请在 team_2 分组讨论方案", "urgency": "normal"},
        },
        created_by="boss",
    )
    discuss_actors = {item.get("actor_id") for item in discuss.get("published_events", [])}
    assert "agent_3" in discuss_actors
    assert "agent_4" in discuss_actors

    direct_reply = runtime.direct_chat_with_agent(
        session_id=session_id,
        agent_id="agent_3",
        text="你现在在忙什么？",
        scope="group:main",
    )
    assert direct_reply is not None
    assert direct_reply.get("action_id") == "direct_reply"
    assert direct_reply.get("actor_id") == "agent_3"
    runtime.close()

