from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from langgraph.types import Send

from graphchat.application.state import WorldState
from graphchat.domain.models.schemas import validate_event
from graphchat.infrastructure.persistence.event_store import JsonlEventStore
from graphchat.infrastructure.persistence.scope_registry import DmRegistry, GroupRegistry


@dataclass
class WorldNodeDeps:
    event_store: JsonlEventStore
    run_agent: Callable[[str, dict], list[dict]]
    group_registry: GroupRegistry | None = None
    dm_registry: DmRegistry | None = None


def ingest_events_node(state: WorldState) -> WorldState:
    pending = list(state.get("pending_events", []))
    incoming = state.get("incoming_events", [])
    valid_incoming: list[dict] = []
    errors: list[str] = []
    for event in incoming:
        parsed, err = validate_event(event)
        if err:
            errors.append(f"ingest_events: invalid incoming event: {err}")
            continue
        valid_incoming.append(parsed)
    pending.extend(valid_incoming)
    patch: WorldState = {"pending_events": pending, "incoming_events": []}
    if errors:
        patch["errors"] = errors
    return patch


def _visible_agents_for_scope(
    *,
    event_scope: str,
    agents: list[str],
    group_registry: GroupRegistry | None,
    dm_registry: DmRegistry | None,
) -> set[str]:
    if event_scope == "group:main":
        if group_registry is not None:
            members = group_registry.members("main")
            if members:
                return {agent_id for agent_id in agents if agent_id in members}
        return set(agents)

    if event_scope.startswith("group:"):
        group_id = event_scope.split(":", maxsplit=1)[1]
        if group_registry is not None:
            members = group_registry.members(group_id)
            return {agent_id for agent_id in agents if agent_id in members}
        return set(agents)

    if event_scope.startswith("dm:"):
        parts = event_scope.split(":")
        if len(parts) != 3:
            return set()
        a, b = parts[1], parts[2]
        if dm_registry is not None and not dm_registry.is_allowed(a, b):
            return set()
        return {agent_id for agent_id in agents if agent_id in {a, b}}

    return set()


def route_scope_node(state: WorldState, deps: WorldNodeDeps) -> WorldState:
    pending = list(state.get("pending_events", []))
    agents = list(state.get("agents", []))
    routed: dict[str, list[dict]] = {agent_id: [] for agent_id in agents}
    for event in pending:
        event_scope = str(event.get("world_scope", "group:main"))
        visible_agents = _visible_agents_for_scope(
            event_scope=event_scope,
            agents=agents,
            group_registry=deps.group_registry,
            dm_registry=deps.dm_registry,
        )
        for agent_id in visible_agents:
            routed.setdefault(agent_id, []).append(event)
    return {"routed_events": pending, "routed_events_by_agent": routed}


def select_runnable_agents_node(state: WorldState) -> WorldState:
    agents = list(state.get("agents", []))
    routed_map = state.get("routed_events_by_agent", {})
    if isinstance(routed_map, dict) and routed_map:
        tasks = []
        runnable_agents = []
        for agent_id in agents:
            visible_events = list(routed_map.get(agent_id, []))
            if not visible_events:
                continue
            runnable_agents.append(agent_id)
            tasks.append({"agent_id": agent_id, "visible_events": visible_events})
        return {
            "runnable_agents": runnable_agents,
            "agent_tasks": tasks,
            "agent_outputs": [],
        }

    tasks = [
        {"agent_id": agent_id, "visible_events": list(state.get("routed_events", []))}
        for agent_id in agents
    ]
    return {
        "runnable_agents": agents,
        "agent_tasks": tasks,
        "agent_outputs": [],
    }


def dispatch_router(state: WorldState):
    tasks = state.get("agent_tasks", [])
    if not tasks:
        return "collect_agent_outputs"
    return [
        Send(
            "run_agent",
            {
                "session_id": state["session_id"],
                "agent_task": task,
                "agent_outputs": [],
            },
        )
        for task in tasks
    ]


def run_agent_node(state: WorldState, deps: WorldNodeDeps) -> WorldState:
    task = state.get("agent_task", {})
    if not task:
        return {}
    outputs = deps.run_agent(state["session_id"], task)
    return {"agent_outputs": outputs}


def collect_agent_outputs_node(state: WorldState) -> WorldState:
    # 聚合字段使用 Annotated[operator.add]，这里不要重复回填，避免重复追加。
    return {}


def commit_events_node(state: WorldState, deps: WorldNodeDeps) -> WorldState:
    raw_events = list(state.get("agent_outputs", []))
    if not raw_events:
        return {}

    valid_events: list[dict] = []
    errors: list[str] = []
    for event in raw_events:
        parsed, err = validate_event(event)
        if err:
            errors.append(f"commit_events: invalid output event: {err}")
            continue
        valid_events.append(parsed)

    if not valid_events:
        patch: WorldState = {}
        if errors:
            patch["errors"] = errors
        return patch

    deps.event_store.append_events(state["session_id"], valid_events)
    patch = {"committed_event_ids": [event.get("event_id", "") for event in valid_events]}
    if errors:
        patch["errors"] = errors
    return patch


def publish_updates_node(state: WorldState) -> WorldState:
    return {"published_events": list(state.get("agent_outputs", []))}


def idle_check_node(state: WorldState) -> WorldState:
    return {"tick": int(state.get("tick", 0)) + 1}
