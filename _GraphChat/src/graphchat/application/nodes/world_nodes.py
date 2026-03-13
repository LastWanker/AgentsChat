from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from langgraph.types import Send

from graphchat.application.state import WorldState
from graphchat.application.world.command_handlers import (
    WorldCommandHandler,
    build_builtin_command_handlers,
    build_command_audit_event,
    merge_world_patch,
    utc_now,
)
from graphchat.domain.models.event import Event
from graphchat.domain.models.schemas import validate_event, validate_world_command_payload
from graphchat.infrastructure.persistence.agent_registry import AgentRegistry
from graphchat.infrastructure.persistence.event_store import JsonlEventStore
from graphchat.infrastructure.persistence.scope_registry import DmRegistry, GroupRegistry


@dataclass
class WorldNodeDeps:
    """Dependencies used by world orchestration nodes.

    Extension policy:
    - Add new control-plane behavior by registering a command handler.
    - Keep graph topology stable; avoid routing by hard-coded node ids from outside.
    """

    event_store: JsonlEventStore
    run_agent: Callable[[str, dict], list[dict]]
    group_registry: GroupRegistry | None = None
    dm_registry: DmRegistry | None = None
    agent_registry: AgentRegistry | None = None
    register_agent: Callable[..., dict] | None = None
    set_agent_enabled: Callable[[str, bool], dict | None] | None = None
    set_agent_retrieval_channels: Callable[[str, list[str]], None] | None = None
    list_agent_status: Callable[[str], dict[str, dict]] | None = None
    direct_chat: Callable[[dict], dict | None] | None = None
    command_handlers: dict[str, WorldCommandHandler] | None = None


_MENTION_RE = re.compile(r"@([A-Za-z0-9_\-]+)")


def ingest_world_commands_node(state: WorldState, deps: WorldNodeDeps) -> WorldState:
    builtin_handlers = build_builtin_command_handlers()
    handlers = dict(builtin_handlers)
    if isinstance(deps.command_handlers, dict):
        # Allow runtime/product layer to register custom commands without editing this file.
        handlers.update(deps.command_handlers)
    extension_types = set(handlers.keys()) - set(builtin_handlers.keys())

    commands = state.get("world_commands", [])
    if not isinstance(commands, list) or not commands:
        return {"world_commands": []}

    valid_commands: list[dict] = []
    errors: list[str] = []
    for raw in commands:
        command_type = str(raw.get("type", "")).strip()
        parsed, err = validate_world_command_payload(raw)
        if err:
            if command_type in extension_types:
                valid_commands.append(
                    {
                        "command_id": str(raw.get("command_id", "") or f"wc_ext_{len(valid_commands)+1}"),
                        "type": command_type,
                        "session_id": str(raw.get("session_id", state.get("session_id", ""))),
                        "scope": str(raw.get("scope", "group:main")),
                        "payload": dict(raw.get("payload", {})) if isinstance(raw.get("payload"), dict) else {},
                        "priority": int(raw.get("priority", 50)),
                        "created_by": str(raw.get("created_by", "system")),
                        "created_at": str(raw.get("created_at", utc_now())),
                    }
                )
                continue
            errors.append(f"ingest_world_commands: invalid command: {err}")
            continue
        valid_commands.append(parsed or {})

    valid_commands.sort(
        key=lambda item: (
            int(item.get("priority", 50)),
            str(item.get("created_at", "")),
            str(item.get("command_id", "")),
        )
    )

    out: WorldState = {
        "world_commands": [],
        "pending_direct_chats": list(state.get("pending_direct_chats", [])),
        "pending_injections": list(state.get("pending_injections", [])),
        "pending_mentions": list(state.get("pending_mentions", [])),
        "world_outputs": list(state.get("world_outputs", [])),
    }
    applied_rows: list[dict] = []

    for command in valid_commands:
        command_type = str(command.get("type", "")).strip()
        handler = handlers.get(command_type)
        if handler is None:
            msg = f"ingest_world_commands: unsupported command type: {command_type}"
            errors.append(msg)
            out["world_outputs"] = list(out.get("world_outputs", [])) + [
                build_command_audit_event(
                    session_id=state.get("session_id", ""),
                    command=command,
                    status="rejected",
                    detail={"error": msg},
                )
            ]
            continue

        patch = handler(command, state, deps)
        out = merge_world_patch(out, patch)
        applied_rows.append(
            {
                "command_id": str(command.get("command_id", "")),
                "type": command_type,
                "applied_at": str(command.get("created_at", "")),
            }
        )
        out["world_outputs"] = list(out.get("world_outputs", [])) + [
            build_command_audit_event(
                session_id=state.get("session_id", ""),
                command=command,
                status="applied",
            )
        ]

    out["applied_world_commands"] = applied_rows
    if errors:
        out["errors"] = errors
    return out


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


def refresh_registry_and_scope_node(state: WorldState, deps: WorldNodeDeps) -> WorldState:
    agents = list(state.get("agents", []))
    if deps.agent_registry is not None:
        agents = deps.agent_registry.enabled_agent_ids()
    status = {}
    if deps.list_agent_status is not None:
        status = deps.list_agent_status(str(state.get("session_id", "")))
    return {"agents": agents, "agent_status_map": status}


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


def _build_injection_event(*, session_id: str, item: dict, target_agent: str) -> dict:
    event = Event(
        session_id=session_id,
        world_scope=str(item.get("target_scope", "group:main")),
        actor_id=str(item.get("created_by", "world")),
        action_id="inject_task",
        action_version="1.0.0",
        payload={
            "text": str(item.get("text", "")),
            "urgency": str(item.get("urgency", "normal")),
            "phase_override": item.get("phase_override"),
            "target_agent": target_agent,
            "source_command_id": str(item.get("command_id", "")),
        },
        trace={"node": "schedule_agent_tasks"},
    )
    return event.to_dict()


def schedule_agent_tasks_node(state: WorldState, deps: WorldNodeDeps) -> WorldState:
    agents = list(state.get("agents", []))
    routed_map = state.get("routed_events_by_agent", {})
    task_map: dict[str, dict] = {agent_id: {"agent_id": agent_id, "visible_events": []} for agent_id in agents}

    if isinstance(routed_map, dict):
        for agent_id in agents:
            for event in list(routed_map.get(agent_id, [])):
                task_map[agent_id]["visible_events"].append(event)

    mentions = state.get("pending_mentions", [])
    if isinstance(mentions, list):
        for item in mentions:
            if not isinstance(item, dict):
                continue
            agent_id = str(item.get("target_agent", "")).strip()
            event = item.get("event", {})
            if agent_id in task_map and isinstance(event, dict):
                task_map[agent_id]["visible_events"].append(event)

    injections = state.get("pending_injections", [])
    if isinstance(injections, list):
        for item in injections:
            if not isinstance(item, dict):
                continue
            targets = item.get("target_agents", [])
            target_set: set[str] = set()
            if isinstance(targets, list):
                target_set = {str(agent_id).strip() for agent_id in targets if str(agent_id).strip()}
            target_scope = str(item.get("target_scope", "group:main"))
            if not target_set:
                target_set = _visible_agents_for_scope(
                    event_scope=target_scope,
                    agents=agents,
                    group_registry=deps.group_registry,
                    dm_registry=deps.dm_registry,
                )
            for agent_id in sorted(target_set):
                if agent_id not in task_map:
                    continue
                task_map[agent_id]["visible_events"].append(
                    _build_injection_event(
                        session_id=str(state.get("session_id", "")),
                        item=item,
                        target_agent=agent_id,
                    )
                )
                phase_override = item.get("phase_override")
                if phase_override:
                    task_map[agent_id]["phase_override"] = str(phase_override)

    tasks = []
    runnable_agents = []
    for agent_id in agents:
        task = task_map[agent_id]
        if task.get("visible_events") or task.get("phase_override"):
            runnable_agents.append(agent_id)
            tasks.append(task)

    return {
        "runnable_agents": runnable_agents,
        "agent_tasks": tasks,
        "agent_outputs": [],
        "pending_events": [],
        "pending_mentions": [],
        "pending_injections": [],
    }


def select_runnable_agents_node(state: WorldState) -> WorldState:
    """V1 compatibility helper for legacy tests."""

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


def collect_agent_outputs_node(_state: WorldState) -> WorldState:
    return {}


def _parse_mentions(text: str) -> list[str]:
    return [item for item in _MENTION_RE.findall(text) if item.strip()]


def broker_mentions_and_replies_node(state: WorldState, deps: WorldNodeDeps) -> WorldState:
    agents = list(state.get("agents", []))
    raw_events = [item for item in state.get("agent_outputs", []) if isinstance(item, dict)]
    world_outputs = list(state.get("world_outputs", []))
    pending_mentions = list(state.get("pending_mentions", []))
    errors: list[str] = []

    for event in raw_events:
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        text = str(payload.get("text", "")).strip()
        if not text:
            continue
        scope = str(event.get("world_scope", "group:main"))
        visible = _visible_agents_for_scope(
            event_scope=scope,
            agents=agents,
            group_registry=deps.group_registry,
            dm_registry=deps.dm_registry,
        )
        actor_id = str(event.get("actor_id", ""))
        for target_agent in _parse_mentions(text):
            if target_agent == actor_id:
                continue
            if target_agent not in visible:
                errors.append(f"mention_broker: target out of scope @{target_agent} in {scope}")
                continue
            request = {
                "request_id": f"mention_{event.get('event_id', '')}_{target_agent}",
                "session_id": str(state.get("session_id", "")),
                "agent_id": target_agent,
                "text": text,
                "scope": scope,
                "actor_id": actor_id,
                "mode": "mention_reply",
                "source_event_id": event.get("event_id"),
            }
            if deps.direct_chat is not None:
                reply = deps.direct_chat(request)
                if isinstance(reply, dict):
                    parsed, err = validate_event(reply)
                    if err:
                        errors.append(f"mention_broker: invalid direct reply: {err}")
                    elif parsed is not None:
                        world_outputs.append(parsed)
                    continue

            mention_event = Event(
                session_id=str(state.get("session_id", "")),
                world_scope=scope,
                actor_id=actor_id,
                action_id="ask_agent",
                action_version="1.0.0",
                payload={
                    "text": text,
                    "mention_target": target_agent,
                    "source_event_id": event.get("event_id"),
                },
                trace={"node": "broker_mentions_and_replies"},
            )
            pending_mentions.append({"target_agent": target_agent, "event": mention_event.to_dict()})

    direct_chats = state.get("pending_direct_chats", [])
    if isinstance(direct_chats, list):
        for request in direct_chats:
            if not isinstance(request, dict):
                continue
            if deps.direct_chat is None:
                pending_mentions.append(
                    {
                        "target_agent": str(request.get("agent_id", "")),
                        "event": Event(
                            session_id=str(state.get("session_id", "")),
                            world_scope=str(request.get("scope", "group:main")),
                            actor_id=str(request.get("actor_id", "world")),
                            action_id="ask_agent",
                            action_version="1.0.0",
                            payload={"text": str(request.get("text", ""))},
                            trace={"node": "broker_mentions_and_replies"},
                        ).to_dict(),
                    }
                )
                continue
            reply = deps.direct_chat(request)
            if not isinstance(reply, dict):
                continue
            parsed, err = validate_event(reply)
            if err:
                errors.append(f"direct_chat: invalid direct reply: {err}")
                continue
            if parsed is not None:
                world_outputs.append(parsed)

    patch: WorldState = {
        "pending_direct_chats": [],
        "pending_mentions": pending_mentions,
        "world_outputs": world_outputs,
    }
    if errors:
        patch["errors"] = errors
    return patch


def commit_events_node(state: WorldState, deps: WorldNodeDeps) -> WorldState:
    raw_events = [item for item in state.get("world_outputs", []) if isinstance(item, dict)]
    raw_events.extend(item for item in state.get("agent_outputs", []) if isinstance(item, dict))
    if not raw_events:
        return {"latest_events": [], "world_outputs": []}

    committed = {str(item) for item in state.get("committed_event_ids", [])}
    deduped: list[dict] = []
    for event in raw_events:
        event_id = str(event.get("event_id", "")).strip()
        if not event_id or event_id in committed:
            continue
        committed.add(event_id)
        deduped.append(event)
    if not deduped:
        return {"latest_events": [], "world_outputs": []}

    valid_events: list[dict] = []
    errors: list[str] = []
    for event in deduped:
        parsed, err = validate_event(event)
        if err:
            errors.append(f"commit_events: invalid output event: {err}")
            continue
        valid_events.append(parsed)

    if not valid_events:
        patch: WorldState = {"latest_events": [], "world_outputs": []}
        if errors:
            patch["errors"] = errors
        return patch

    deps.event_store.append_events(state["session_id"], valid_events)
    patch: WorldState = {
        "committed_event_ids": [event.get("event_id", "") for event in valid_events],
        "latest_events": valid_events,
        "world_outputs": [],
    }
    if errors:
        patch["errors"] = errors
    return patch


def publish_updates_node(state: WorldState) -> WorldState:
    return {"published_events": list(state.get("latest_events", []))}


def world_loop_gate_node(state: WorldState) -> WorldState:
    world_tick = int(state.get("world_tick", state.get("tick", 0))) + 1
    max_ticks = max(1, int(state.get("max_world_ticks_per_run", 1)))
    world_running = bool(state.get("world_running", False))
    stop_requested = bool(state.get("stop_requested", False))
    has_pending_work = bool(
        state.get("pending_events")
        or state.get("pending_mentions")
        or state.get("pending_injections")
        or state.get("pending_direct_chats")
        or state.get("world_commands")
    )
    loop_continue = world_running and (not stop_requested) and world_tick < max_ticks and has_pending_work
    return {
        "world_tick": world_tick,
        "tick": world_tick,
        "loop_continue": loop_continue,
    }


def world_loop_router(state: WorldState) -> str:
    return "ingest_world_commands" if bool(state.get("loop_continue", False)) else "__end__"
