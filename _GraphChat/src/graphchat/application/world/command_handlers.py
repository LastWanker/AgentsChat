from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

from graphchat.application.state import WorldState
from graphchat.domain.models.event import Event

if TYPE_CHECKING:
    from graphchat.application.nodes.world_nodes import WorldNodeDeps


WorldCommandHandler = Callable[[dict, WorldState, "WorldNodeDeps"], WorldState]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def merge_world_patch(base: WorldState, patch: WorldState) -> WorldState:
    """Merge state patches with list/dict append semantics for orchestration queues."""

    merged: WorldState = dict(base)
    for key, value in patch.items():
        if isinstance(value, list) and isinstance(merged.get(key), list):
            merged[key] = list(merged.get(key, [])) + list(value)  # type: ignore[assignment]
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            item = dict(merged.get(key, {}))
            item.update(value)
            merged[key] = item  # type: ignore[assignment]
            continue
        merged[key] = value  # type: ignore[assignment]
    return merged


def build_command_audit_event(*, session_id: str, command: dict, status: str, detail: dict | None = None) -> dict:
    event = Event(
        session_id=session_id,
        world_scope=str(command.get("scope", "group:main")),
        actor_id=str(command.get("created_by", "world")),
        action_id="world_command_applied",
        action_version="1.0.0",
        payload={
            "command_id": str(command.get("command_id", "")),
            "type": str(command.get("type", "")),
            "status": status,
            "detail": detail or {},
        },
        trace={"node": "ingest_world_commands"},
    )
    return event.to_dict()


def normalize_phase(value: str | None) -> str:
    phase = str(value or "").strip().lower()
    if phase in {"force_listening", "listening"}:
        return "force_listening"
    if phase in {"force_emit", "emit"}:
        return "force_emit"
    return "force_plan"


def _handle_create_agent(command: dict, _state: WorldState, deps: "WorldNodeDeps") -> WorldState:
    payload = command.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    agent_id = str(payload.get("agent_id", "")).strip()
    if not agent_id:
        return {"errors": ["ingest_world_commands: create_agent missing payload.agent_id"]}

    if deps.register_agent is not None:
        deps.register_agent(
            agent_id=agent_id,
            enabled=bool(payload.get("enabled", True)),
            role=str(payload.get("role", "member")),
            permissions=list(payload.get("permissions", [])) if isinstance(payload.get("permissions"), list) else [],
            join_main_group=bool(payload.get("join_main_group", True)),
        )
        return {}

    if deps.agent_registry is None:
        return {"errors": ["ingest_world_commands: create_agent requires agent registry"]}

    deps.agent_registry.upsert_agent(
        agent_id=agent_id,
        enabled=bool(payload.get("enabled", True)),
        role=str(payload.get("role", "member")),
        permissions=list(payload.get("permissions", [])) if isinstance(payload.get("permissions"), list) else [],
    )
    if deps.group_registry is not None and bool(payload.get("join_main_group", True)):
        deps.group_registry.add_member("main", agent_id)
    return {}


def _handle_set_enabled(command: dict, _state: WorldState, deps: "WorldNodeDeps", enabled: bool) -> WorldState:
    payload = command.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    agent_id = str(payload.get("agent_id", "")).strip()
    if not agent_id:
        return {"errors": [f"ingest_world_commands: {command.get('type')} missing payload.agent_id"]}

    if deps.set_agent_enabled is not None:
        deps.set_agent_enabled(agent_id, enabled)
        return {}
    if deps.agent_registry is not None:
        deps.agent_registry.set_enabled(agent_id, enabled)
        return {}
    return {"errors": [f"ingest_world_commands: {command.get('type')} requires registry support"]}


def _handle_upsert_group(command: dict, _state: WorldState, deps: "WorldNodeDeps") -> WorldState:
    payload = command.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    group_id = str(payload.get("group_id", "")).strip()
    members = payload.get("members", [])
    if not group_id:
        return {"errors": ["ingest_world_commands: upsert_group missing payload.group_id"]}
    if not isinstance(members, list):
        return {"errors": ["ingest_world_commands: upsert_group payload.members must be list"]}
    if deps.group_registry is None:
        return {"errors": ["ingest_world_commands: upsert_group requires group_registry"]}
    deps.group_registry.set_members(group_id, [str(item) for item in members])
    return {}


def _handle_upsert_dm_pair(command: dict, _state: WorldState, deps: "WorldNodeDeps") -> WorldState:
    payload = command.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    a = str(payload.get("a", "")).strip()
    b = str(payload.get("b", "")).strip()
    enabled = bool(payload.get("enabled", True))
    if not a or not b:
        return {"errors": ["ingest_world_commands: upsert_dm_pair requires payload.a and payload.b"]}
    if deps.dm_registry is None:
        return {"errors": ["ingest_world_commands: upsert_dm_pair requires dm_registry"]}
    if enabled:
        deps.dm_registry.register_pair(a, b)
    else:
        deps.dm_registry.revoke_pair(a, b)
    return {}


def _handle_inject_task(command: dict, _state: WorldState, _deps: "WorldNodeDeps") -> WorldState:
    payload = command.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    urgency = str(payload.get("urgency", "normal")).strip().lower()
    if urgency not in {"normal", "urgent"}:
        urgency = "normal"
    target_agents = payload.get("target_agents", [])
    if not isinstance(target_agents, list):
        target_agents = []

    phase_override = payload.get("phase_override")
    if urgency == "urgent" and not phase_override:
        phase_override = "force_plan"

    item = {
        "command_id": str(command.get("command_id", "")),
        "target_scope": str(command.get("scope", "group:main")),
        "target_agents": [str(item) for item in target_agents if str(item).strip()],
        "text": str(payload.get("text", "")).strip(),
        "urgency": urgency,
        "phase_override": normalize_phase(str(phase_override)) if phase_override else None,
        "created_by": str(command.get("created_by", "world")),
        "created_at": str(command.get("created_at", utc_now())),
    }
    return {"pending_injections": [item]}


def _handle_direct_chat(command: dict, _state: WorldState, _deps: "WorldNodeDeps") -> WorldState:
    payload = command.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    targets_raw = payload.get("target_agents")
    targets: list[str] = []
    if isinstance(targets_raw, list):
        targets = [str(item).strip() for item in targets_raw if str(item).strip()]
    elif str(payload.get("agent_id", "")).strip():
        targets = [str(payload.get("agent_id", "")).strip()]
    if not targets:
        return {"errors": ["ingest_world_commands: direct_chat requires payload.agent_id or payload.target_agents"]}

    rows = []
    for agent_id in targets:
        rows.append(
            {
                "request_id": f"dc_{command.get('command_id', '')}_{agent_id}",
                "session_id": str(command.get("session_id", "")),
                "agent_id": agent_id,
                "text": str(payload.get("text", "")).strip(),
                "scope": str(command.get("scope", "group:main")),
                "actor_id": str(command.get("created_by", "world")),
                "mode": "direct_chat",
                "source_command_id": str(command.get("command_id", "")),
            }
        )
    return {"pending_direct_chats": rows}


def _handle_force_phase(command: dict, _state: WorldState, _deps: "WorldNodeDeps") -> WorldState:
    payload = command.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    target_agents = payload.get("target_agents", [])
    if not isinstance(target_agents, list):
        target_agents = []
    agent_id = str(payload.get("agent_id", "")).strip()
    if agent_id:
        target_agents.append(agent_id)
    item = {
        "command_id": str(command.get("command_id", "")),
        "target_scope": str(command.get("scope", "group:main")),
        "target_agents": [str(item).strip() for item in target_agents if str(item).strip()],
        "text": str(payload.get("reason", "")).strip(),
        "urgency": "urgent",
        "phase_override": normalize_phase(str(payload.get("phase", "force_plan"))),
        "created_by": str(command.get("created_by", "world")),
        "created_at": str(command.get("created_at", utc_now())),
    }
    return {"pending_injections": [item]}


def _handle_set_agent_retrieval(command: dict, _state: WorldState, deps: "WorldNodeDeps") -> WorldState:
    payload = command.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    agent_id = str(payload.get("agent_id", "")).strip()
    channels = payload.get("channels", [])
    if not agent_id:
        return {"errors": ["ingest_world_commands: set_agent_retrieval requires payload.agent_id"]}
    if not isinstance(channels, list):
        return {"errors": ["ingest_world_commands: set_agent_retrieval payload.channels must be list"]}
    setter = getattr(deps, "set_agent_retrieval_channels", None)
    if callable(setter):
        setter(agent_id, [str(item) for item in channels])
        return {}
    return {"errors": ["ingest_world_commands: set_agent_retrieval requires runtime support"]}


def _handle_stop_world(command: dict, _state: WorldState, _deps: "WorldNodeDeps") -> WorldState:
    payload = command.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    return {
        "stop_requested": True,
        "world_running": False,
        "stop_reason": str(payload.get("reason", "stop_world")),
    }


def build_builtin_command_handlers() -> dict[str, WorldCommandHandler]:
    return {
        "create_agent": _handle_create_agent,
        "enable_agent": lambda command, state, deps: _handle_set_enabled(command, state, deps, True),
        "disable_agent": lambda command, state, deps: _handle_set_enabled(command, state, deps, False),
        "upsert_group": _handle_upsert_group,
        "upsert_dm_pair": _handle_upsert_dm_pair,
        "inject_task": _handle_inject_task,
        "direct_chat": _handle_direct_chat,
        "force_phase": _handle_force_phase,
        "set_agent_retrieval": _handle_set_agent_retrieval,
        "stop_world": _handle_stop_world,
    }

