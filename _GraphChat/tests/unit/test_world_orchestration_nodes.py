from __future__ import annotations

from graphchat.application.nodes.world_nodes import (
    WorldNodeDeps,
    broker_mentions_and_replies_node,
    schedule_agent_tasks_node,
)
from graphchat.domain.models.event import Event
from graphchat.infrastructure.persistence.event_store import JsonlEventStore
from graphchat.infrastructure.persistence.scope_registry import DmRegistry, GroupRegistry


def test_schedule_agent_tasks_should_apply_urgent_phase_override(tmp_path) -> None:
    deps = WorldNodeDeps(
        event_store=JsonlEventStore(tmp_path / "sessions"),
        run_agent=lambda _session_id, _task: [],
        group_registry=GroupRegistry(tmp_path / "registries" / "groups.json", bootstrap_agents=["agent_1"]),
        dm_registry=DmRegistry(tmp_path / "registries" / "dm.json"),
    )
    state = {
        "session_id": "s_urgent",
        "agents": ["agent_1"],
        "routed_events_by_agent": {"agent_1": []},
        "pending_mentions": [],
        "pending_injections": [
            {
                "command_id": "wc_urgent",
                "target_scope": "group:main",
                "target_agents": ["agent_1"],
                "text": "urgent task",
                "urgency": "urgent",
                "phase_override": "force_plan",
                "created_by": "boss",
            }
        ],
    }
    out = schedule_agent_tasks_node(state, deps)
    assert out.get("runnable_agents") == ["agent_1"]
    assert len(out.get("agent_tasks", [])) == 1
    assert out["agent_tasks"][0].get("phase_override") == "force_plan"
    assert out.get("pending_injections") == []


def test_broker_mentions_should_reject_out_of_scope_targets(tmp_path) -> None:
    group_registry = GroupRegistry(tmp_path / "registries" / "groups.json", bootstrap_agents=["agent_1", "agent_2"])
    group_registry.set_members("team", ["agent_1"])
    deps = WorldNodeDeps(
        event_store=JsonlEventStore(tmp_path / "sessions"),
        run_agent=lambda _session_id, _task: [],
        group_registry=group_registry,
        dm_registry=DmRegistry(tmp_path / "registries" / "dm.json"),
    )
    speak = Event(
        session_id="s_scope",
        world_scope="group:team",
        actor_id="agent_1",
        action_id="speak",
        action_version="1.0.0",
        payload={"text": "@agent_2 please check"},
        trace={"node": "emit_event"},
    ).to_dict()
    state = {
        "session_id": "s_scope",
        "agents": ["agent_1", "agent_2"],
        "agent_outputs": [speak],
        "world_outputs": [],
        "pending_mentions": [],
        "pending_direct_chats": [],
    }
    out = broker_mentions_and_replies_node(state, deps)
    assert any("target out of scope" in item for item in out.get("errors", []))
    assert out.get("pending_mentions", []) == []

