from __future__ import annotations

from graphchat.application.nodes.world_nodes import (
    WorldNodeDeps,
    route_scope_node,
    select_runnable_agents_node,
)
from graphchat.infrastructure.persistence.event_store import JsonlEventStore
from graphchat.infrastructure.persistence.scope_registry import DmRegistry, GroupRegistry


def _dummy_run_agent(_session_id: str, _task: dict) -> list[dict]:
    return []


def test_route_scope_should_split_group_and_dm_visibility(tmp_path) -> None:
    base_dir = tmp_path / "runtime"
    group_registry = GroupRegistry(base_dir / "group_registry.json", bootstrap_agents=["agent_1", "agent_2", "agent_3"])
    group_registry.set_members("alpha", ["agent_2"])
    dm_registry = DmRegistry(base_dir / "dm_registry.json")
    dm_registry.register_pair("agent_1", "agent_3")

    deps = WorldNodeDeps(
        event_store=JsonlEventStore(tmp_path / "sessions"),
        run_agent=_dummy_run_agent,
        group_registry=group_registry,
        dm_registry=dm_registry,
    )
    state = {
        "agents": ["agent_1", "agent_2", "agent_3"],
        "pending_events": [
            {"event_id": "e1", "world_scope": "group:main"},
            {"event_id": "e2", "world_scope": "group:alpha"},
            {"event_id": "e3", "world_scope": "dm:agent_1:agent_3"},
        ],
    }
    routed = route_scope_node(state, deps)
    routed_map = routed["routed_events_by_agent"]
    assert [e["event_id"] for e in routed_map["agent_1"]] == ["e1", "e3"]
    assert [e["event_id"] for e in routed_map["agent_2"]] == ["e1", "e2"]
    assert [e["event_id"] for e in routed_map["agent_3"]] == ["e1", "e3"]

    selected = select_runnable_agents_node({**state, **routed})
    task_ids = {task["agent_id"] for task in selected["agent_tasks"]}
    assert task_ids == {"agent_1", "agent_2", "agent_3"}
