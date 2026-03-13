from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1

from langgraph.types import interrupt

from graphchat.application.state import AgentState
from graphchat.domain.models.action_contract import ActionSpec
from graphchat.domain.models.event import Event


@dataclass
class AgentNodeDeps:
    action_registry: dict[str, ActionSpec]
    model_provider: object
    idempotency_cache: set[str]


def listening_node(state: AgentState) -> AgentState:
    visible_events = state.get("visible_events", [])
    last_event = visible_events[-1] if visible_events else {}
    return {"last_event": last_event, "trace": {"node": "listening"}}


def decide_wake_node(state: AgentState) -> AgentState:
    phase_override = str(state.get("phase_override", "")).strip().lower()
    if phase_override in {"force_plan", "force_emit"}:
        return {"should_wake": True}
    if str(state.get("agent_status", "")).lower() == "sleeping":
        return {"should_wake": False}
    return {"should_wake": bool(state.get("should_wake", False))}


def decide_wake_router(state: AgentState) -> str:
    return "plan_action" if state.get("should_wake") else "__end__"


def plan_action_node(state: AgentState, deps: AgentNodeDeps) -> AgentState:
    # 模型层约束：优先走 LangChain 结构化输出，不可用时回退规则模型。
    plan = deps.model_provider.plan_action(state)
    if not isinstance(plan, dict):
        plan = {"action": "listen_only", "payload": {"reason": "invalid_model_output"}}
    task_done = bool(plan.get("task_done", False))

    # V2 主路径：actions[]
    planned_actions = plan.get("actions", [])
    if not isinstance(planned_actions, list):
        planned_actions = []

    normalized_actions: list[dict] = []
    for item in planned_actions:
        if not isinstance(item, dict):
            continue
        action_id = str(item.get("action_id") or "").strip()
        payload = item.get("payload", {})
        if not action_id:
            continue
        if not isinstance(payload, dict):
            payload = {}
        normalized_actions.append({**item, "action_id": action_id, "payload": payload})

    # V1 兼容路径：action/payload -> actions[0]
    if not normalized_actions:
        action = str(plan.get("action", "listen_only") or "listen_only")
        payload = plan.get("payload", {})
        if not isinstance(payload, dict):
            payload = {"reason": "invalid_model_payload"}
        normalized_actions = [
            {
                "action_id": action,
                "plan_text": "[compat] from V1 action/payload",
                "payload": payload,
                "target_scope": str(payload.get("world_scope", "group:main")),
                "target_agents": [],
                "priority": 100,
                "can_skip": False,
                "step_index": 1,
            }
        ]

    head = normalized_actions[0]
    action = str(head.get("action_id") or "listen_only")
    payload = head.get("payload", {})
    if not isinstance(payload, dict):
        payload = {"reason": "invalid_model_payload"}
    spec = deps.action_registry.get(action)

    idempotency_seed = f"{state.get('session_id')}|{state.get('agent_id')}|{action}|{state.get('last_event', {}).get('event_id', '')}"
    idempotency_key = sha1(idempotency_seed.encode("utf-8")).hexdigest()[:16]

    return {
        # V2 主字段
        "planned_actions": normalized_actions,
        "task_done": task_done,
        # V1 兼容字段（过渡期保留）
        "planned_action": action,
        "action_payload": payload,
        "citation_policy": spec.citation_policy if spec else "none",
        "needs_retrieval": bool(spec.needs_retrieval) if spec else False,
        "approval_required": bool(spec.approval_policy == "boss_required") if spec else False,
        "idempotency_key": idempotency_key,
        "trace": {"node": "plan_action"},
    }


def retrieval_router(state: AgentState) -> str:
    return "retrieval_subgraph" if state.get("needs_retrieval") else "citation_guard"


def governance_router(state: AgentState) -> str:
    action = str(state.get("planned_action", "")).strip()
    return "governance_subgraph" if action in {"vote_decision", "dissolve_group"} else "guardrail_subgraph"


def lifecycle_gate_node(state: AgentState) -> AgentState:
    ttl = int(state.get("global_ttl", 0))
    threshold = int(state.get("lastlife_threshold", 3))
    if ttl <= 0:
        return {"agent_status": "sleeping"}
    if ttl <= threshold:
        return {"agent_status": "lastlife"}
    if state.get("task_done", False):
        return {"agent_status": "idle"}
    return {"agent_status": "working"}


def lifecycle_router(state: AgentState) -> str:
    if str(state.get("agent_status", "")).lower() == "sleeping":
        return "__end__"
    if not bool(state.get("enable_internal_loop", False)):
        return "__end__"
    if bool(state.get("task_done", False)):
        return "listening_subgraph"
    return "decide_wake"


def policy_gate_node(state: AgentState) -> AgentState:
    if not state.get("approval_required"):
        return {}
    if not state.get("approval_decision"):
        decision = interrupt(
            {
                "type": "boss_review",
                "agent_id": state.get("agent_id"),
                "planned_action": state.get("planned_action"),
                "payload": state.get("action_payload", {}),
            }
        )
        if isinstance(decision, dict):
            return {"approval_decision": str(decision.get("decision", "approve"))}
        return {"approval_decision": str(decision)}

    if state.get("approval_decision", "approve").lower() not in {"approve", "approved", "allow"}:
        return {
            "planned_action": "listen_only",
            "action_payload": {"reason": "boss_rejected"},
            "errors": [f"policy_gate: boss rejected {state.get('planned_action')}"],
        }
    return {}


def emit_event_node(state: AgentState, deps: AgentNodeDeps) -> AgentState:
    key = state.get("idempotency_key", "")
    if key and key in deps.idempotency_cache:
        return {"errors": [f"emit_event skipped by idempotency key {key}"]}
    if key:
        deps.idempotency_cache.add(key)

    actions = [item for item in state.get("action_results", []) if isinstance(item, dict)]
    if not actions:
        actions = [
            {
                "action_id": state.get("planned_action", "listen_only"),
                "payload": state.get("action_payload", {}),
                "step_index": 1,
            }
        ]

    emitted: list[dict] = []
    for idx, item in enumerate(actions):
        action = str(item.get("action_id", "listen_only") or "listen_only")
        payload = item.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}
        spec = deps.action_registry.get(action)
        event = Event(
            session_id=state["session_id"],
            world_scope=payload.get("world_scope", "group:main"),
            actor_id=state["agent_id"],
            action_id=action,
            action_version=spec.version if spec else "1.0.0",
            payload=payload,
            references=[
                {"event_id": event_id, "role": "support", "score": 0.5}
                for event_id in state.get("support_references", [])
            ],
            focus_reference=state.get("focus_reference"),
            trace={
                "node": "emit_event",
                "idempotency_key": key,
                "batch_index": idx,
                "step_index": item.get("step_index"),
                "retrieval_channel": state.get("retrieval_channel"),
                "retrieval_channels": list(state.get("retrieval_channels", [])),
            },
        )
        emitted.append(event.to_dict())
    return {"emitted_events": emitted}
