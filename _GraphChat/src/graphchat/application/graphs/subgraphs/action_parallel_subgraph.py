from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
import operator
from typing import Any, TypedDict
from typing_extensions import Annotated

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from graphchat.application.guards.action_registry_guard import action_registry_guard_node
from graphchat.application.guards.citation_guard import citation_guard_node
from graphchat.application.guards.idempotency_guard import idempotency_guard_node
from graphchat.application.guards.schema_guard import schema_guard_node
from graphchat.application.nodes.agent_nodes import policy_gate_node
from graphchat.application.skills.guard_profiles import (
    SkillGuardProfile,
    default_profile_for_action,
)
from graphchat.domain.models.action_contract import ActionSpec
from graphchat.domain.models.event import Event
from graphchat.domain.models.planning_schema import normalize_actions_v2


@dataclass
class ActionParallelDeps:
    allowed_actions: set[str]
    action_registry: dict[str, ActionSpec]
    skill_profiles: dict[str, SkillGuardProfile]
    idempotency_cache: set[str]
    retrieval_subgraph: Any
    board_subgraph: Any
    governance_subgraph: Any
    plan_only: bool = False


class ActionParallelState(TypedDict, total=False):
    session_id: str
    agent_id: str
    visible_events: list[dict]
    last_event: dict
    global_ttl: int
    ttl_initial: int
    enabled_retrieval_channels: list[str]
    planned_actions: list[dict]
    planned_action: str
    action_payload: dict
    task_done: bool
    plan_steps: list[dict]
    executed_step_ids: list[str]
    plan_execution_report: dict
    ready_steps: list[dict]
    current_step: dict
    skill_context: dict
    step_results: Annotated[list[dict], operator.add]
    wave_step_ids: Annotated[list[str], operator.add]
    wave_context_patches: Annotated[list[dict], operator.add]
    action_results: Annotated[list[dict], operator.add]
    emitted_events: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]


def _ensure_payload_scope(payload: dict) -> dict:
    data = dict(payload)
    if "world_scope" not in data:
        data["world_scope"] = "group:main"
    return data


def _sort_steps(rows: list[dict]) -> list[dict]:
    out = [item for item in rows if isinstance(item, dict)]
    out.sort(
        key=lambda x: (
            0 if x.get("step_index") is not None else 1,
            int(x.get("step_index", 999)),
            int(x.get("priority", 100)),
        )
    )
    return out


def _idempotency_key(*, session_id: str, agent_id: str, action_id: str, step_id: str, event_id: str) -> str:
    seed = f"{session_id}|{agent_id}|{action_id}|{step_id}|{event_id}"
    return sha1(seed.encode("utf-8")).hexdigest()[:20]


def _execute_retrieval_stage(
    state: ActionParallelState,
    deps: ActionParallelDeps,
    step: dict,
    *,
    citation_enabled: bool,
) -> tuple[dict, list[str]]:
    payload = _ensure_payload_scope(step.get("payload", {}))
    query = str(payload.get("query") or payload.get("text") or state.get("last_event", {}).get("payload", {}).get("text", ""))
    retrieval_action = str(payload.get("for_action") or step.get("action_id") or "search_web")
    if retrieval_action == "rag":
        retrieval_action = "search_web"
    retrieval_state = {
        "session_id": state.get("session_id", ""),
        "agent_id": state.get("agent_id", ""),
        "visible_events": list(state.get("visible_events", [])),
        "planned_action": retrieval_action,
        "action_payload": {"text": query, "world_scope": payload.get("world_scope", "group:main")},
        "enabled_retrieval_channels": list(state.get("enabled_retrieval_channels", [])),
    }
    rag_out = deps.retrieval_subgraph.invoke(retrieval_state)

    merged = dict(rag_out)
    if citation_enabled:
        citation_policy = str(step.get("citation_policy", payload.get("citation_policy", "required_focus")) or "required_focus")
        cite_patch = citation_guard_node(
            {
                **retrieval_state,
                **rag_out,
                "citation_policy": citation_policy,
                "action_payload": {"world_scope": payload.get("world_scope", "group:main")},
            }
        )
        merged.update(cite_patch)

    errors: list[str] = []
    if merged.get("planned_action") == "listen_only":
        errors.extend([f"rag_step:{item}" for item in merged.get("errors", [])])
    context_patch = {
        "focus_reference": merged.get("focus_reference"),
        "support_references": list(merged.get("support_references", [])),
        "retrieval_channel": merged.get("retrieval_channel"),
        "retrieval_channels": list(merged.get("retrieval_channels", [])),
        "candidates": list(merged.get("candidates", [])),
        "reroute_hint": merged.get("reroute_hint"),
        "retrieval_trace": dict(merged.get("retrieval_trace", {})),
    }
    return context_patch, errors


def _profile_for_step(deps: ActionParallelDeps, action_id: str) -> SkillGuardProfile:
    profile = deps.skill_profiles.get(action_id)
    if profile is not None:
        return profile
    return default_profile_for_action(action_id, deps.action_registry.get(action_id))


def _execute_action_step(state: ActionParallelState, deps: ActionParallelDeps, step: dict) -> tuple[dict, dict | None, list[str]]:
    session_id = str(state.get("session_id", ""))
    agent_id = str(state.get("agent_id", ""))
    step_id = str(step.get("step_id", ""))
    action = str(step.get("action_id", "listen_only") or "listen_only")
    payload = _ensure_payload_scope(step.get("payload", {}))
    context = dict(state.get("skill_context", {}))
    spec = deps.action_registry.get(action)
    profile = _profile_for_step(deps, action)
    citation_policy = str(step.get("citation_policy") or (spec.citation_policy if spec else "none"))
    needs_rag = bool(payload.get("use_rag", False) or profile.run_retrieval)

    working: dict[str, Any] = {
        "session_id": session_id,
        "agent_id": agent_id,
        "planned_action": action,
        "action_payload": payload,
        "citation_policy": citation_policy,
        "visible_events": list(state.get("visible_events", [])),
        "last_event": dict(state.get("last_event", {})),
        "approval_required": bool(spec.approval_policy == "boss_required") if spec else False,
    }
    working.update(context)
    errors: list[str] = []

    if needs_rag:
        rag_context, rag_errors = _execute_retrieval_stage(
            state,
            deps,
            {
                "action_id": action,
                "payload": payload,
                "citation_policy": citation_policy,
            },
            citation_enabled=profile.enable_citation_guard,
        )
        working.update(rag_context)
        if rag_errors:
            errors.extend(rag_errors)

    if profile.run_governance_subgraph:
        gov_out = deps.governance_subgraph.invoke(working)
        working.update(gov_out)
    if profile.run_board_subgraph:
        board_out = deps.board_subgraph.invoke(working)
        working.update(board_out)

    if profile.enable_citation_guard and citation_policy != "none":
        working.update(citation_guard_node(working))
    if profile.enable_policy_guard:
        working.update(policy_gate_node(working))
    if profile.enable_schema_guard:
        working.update(schema_guard_node(working))
    if profile.enable_registry_guard:
        working.update(action_registry_guard_node(working, deps.action_registry))

    event_id = str(state.get("last_event", {}).get("event_id", ""))
    key = _idempotency_key(
        session_id=session_id,
        agent_id=agent_id,
        action_id=str(working.get("planned_action", action)),
        step_id=step_id,
        event_id=event_id,
    )
    if profile.enable_idempotency_guard:
        working["idempotency_key"] = key
        working.update(idempotency_guard_node(working, deps.idempotency_cache))

    final_action = str(working.get("planned_action", "listen_only") or "listen_only")
    final_payload = working.get("action_payload", {})
    if not isinstance(final_payload, dict):
        final_payload = {}

    if final_action == "listen_only":
        errors.extend([str(item) for item in working.get("errors", [])])
        context_patch = {
            "focus_reference": working.get("focus_reference"),
            "support_references": list(working.get("support_references", [])),
            "retrieval_channel": working.get("retrieval_channel"),
            "retrieval_channels": list(working.get("retrieval_channels", [])),
            "candidates": list(working.get("candidates", [])),
            "reroute_hint": working.get("reroute_hint"),
            "retrieval_trace": dict(working.get("retrieval_trace", {})),
        }
        return context_patch, None, errors

    if profile.enable_idempotency_guard and key in deps.idempotency_cache:
        errors.append(f"idempotency_guard: duplicated {key}")
        context_patch = {
            "focus_reference": working.get("focus_reference"),
            "support_references": list(working.get("support_references", [])),
            "retrieval_channel": working.get("retrieval_channel"),
            "retrieval_channels": list(working.get("retrieval_channels", [])),
            "candidates": list(working.get("candidates", [])),
            "reroute_hint": working.get("reroute_hint"),
            "retrieval_trace": dict(working.get("retrieval_trace", {})),
        }
        return context_patch, None, errors

    if profile.enable_idempotency_guard:
        deps.idempotency_cache.add(key)
    if not profile.emit_event:
        context_patch = {
            "focus_reference": working.get("focus_reference"),
            "support_references": list(working.get("support_references", [])),
            "retrieval_channel": working.get("retrieval_channel"),
            "retrieval_channels": list(working.get("retrieval_channels", [])),
            "candidates": list(working.get("candidates", [])),
            "reroute_hint": working.get("reroute_hint"),
            "retrieval_trace": dict(working.get("retrieval_trace", {})),
        }
        errors.extend([str(item) for item in working.get("errors", [])])
        return context_patch, {"event": None, "action_result": None}, errors
    spec_final = deps.action_registry.get(final_action)
    event = Event(
        session_id=session_id,
        world_scope=final_payload.get("world_scope", "group:main"),
        actor_id=agent_id,
        action_id=final_action,
        action_version=spec_final.version if spec_final else "1.0.0",
        payload=final_payload,
        references=[
            {"event_id": event_id, "role": "support", "score": 0.5}
            for event_id in working.get("support_references", [])
        ],
        focus_reference=working.get("focus_reference"),
        trace={
            "node": "execute_plan_subgraph",
            "step_id": step_id,
            "step_index": step.get("step_index"),
            "idempotency_key": key,
            "retrieval_channel": working.get("retrieval_channel"),
            "retrieval_channels": list(working.get("retrieval_channels", [])),
            "guard_profile": profile.skill_id,
        },
    ).to_dict()

    action_result = {
        "step_id": step_id,
        "step_index": step.get("step_index"),
        "action_id": final_action,
        "payload": final_payload,
        "priority": step.get("priority", 100),
        "can_skip": bool(step.get("can_skip", False)),
        "plan_text": str(step.get("plan_text", "")),
    }
    context_patch = {
        "focus_reference": working.get("focus_reference"),
        "support_references": list(working.get("support_references", [])),
        "retrieval_channel": working.get("retrieval_channel"),
        "retrieval_channels": list(working.get("retrieval_channels", [])),
        "candidates": list(working.get("candidates", [])),
        "reroute_hint": working.get("reroute_hint"),
        "retrieval_trace": dict(working.get("retrieval_trace", {})),
    }
    errors.extend([str(item) for item in working.get("errors", [])])
    return context_patch, {"event": event, "action_result": action_result}, errors


def build_action_parallel_subgraph(deps: ActionParallelDeps):
    graph = StateGraph(ActionParallelState)

    def prepare_plan_node(state: ActionParallelState) -> ActionParallelState:
        rows = state.get("planned_actions", [])
        if not isinstance(rows, list):
            rows = []
        normalized = normalize_actions_v2(
            actions=[item for item in rows if isinstance(item, dict)],
            allowed_actions=deps.allowed_actions,
        )
        if not normalized:
            action = str(state.get("planned_action", "listen_only") or "listen_only")
            payload = state.get("action_payload", {})
            if not isinstance(payload, dict):
                payload = {"reason": "invalid_model_payload"}
            normalized = normalize_actions_v2(
                actions=[
                    {
                        "step_id": "s1",
                        "action_id": action,
                        "plan_text": "[compat] fallback from planned_action",
                        "payload": _ensure_payload_scope(payload),
                        "target_scope": str(payload.get("world_scope", "group:main")),
                        "target_agents": [],
                        "depends_on": [],
                        "dispatch": "serial",
                        "priority": 100,
                        "can_skip": False,
                        "step_index": 1,
                    }
                ],
                allowed_actions=deps.allowed_actions,
            )
        return {
            "plan_steps": _sort_steps(normalized),
            "executed_step_ids": [],
            "plan_execution_report": {},
            "ready_steps": [],
            "skill_context": {},
            "step_results": [],
            "wave_step_ids": [],
            "wave_context_patches": [],
            "action_results": [],
            "emitted_events": [],
        }

    def select_ready_steps_node(state: ActionParallelState) -> ActionParallelState:
        steps = _sort_steps(list(state.get("plan_steps", [])))
        executed = {str(item) for item in state.get("executed_step_ids", [])}
        remaining = [item for item in steps if str(item.get("step_id", "")) not in executed]
        if not remaining:
            return {"ready_steps": []}
        ready = [item for item in remaining if set(item.get("depends_on", [])).issubset(executed)]
        errors: list[str] = []
        if not ready:
            ready = [remaining[0]]
            errors.append(
                f"execute_plan: dependency_deadlock_resolved_by_force_step={ready[0].get('step_id', '')}"
            )

        parallel_batch = [item for item in ready if str(item.get("dispatch", "auto")).lower() == "parallel"]
        selected = parallel_batch or [ready[0]]
        patch: ActionParallelState = {"ready_steps": selected}
        if errors:
            patch["errors"] = errors
        return patch

    def dispatch_ready_router(state: ActionParallelState):
        ready = [item for item in state.get("ready_steps", []) if isinstance(item, dict)]
        if not ready:
            return "finalize_plan"
        return [
            Send(
                "execute_step",
                {
                    "session_id": state.get("session_id", ""),
                    "agent_id": state.get("agent_id", ""),
                    "visible_events": list(state.get("visible_events", [])),
                    "last_event": dict(state.get("last_event", {})),
                    "global_ttl": int(state.get("global_ttl", state.get("ttl_initial", 15))),
                    "enabled_retrieval_channels": list(state.get("enabled_retrieval_channels", [])),
                    "skill_context": dict(state.get("skill_context", {})),
                    "current_step": item,
                    "step_results": [],
                    "wave_step_ids": [],
                    "wave_context_patches": [],
                    "action_results": [],
                    "emitted_events": [],
                    "errors": [],
                },
            )
            for item in ready
        ]

    def execute_step_node(state: ActionParallelState) -> ActionParallelState:
        step = state.get("current_step", {})
        if not isinstance(step, dict):
            return {}
        step_id = str(step.get("step_id", "")).strip()
        if not step_id:
            return {}

        ttl = int(state.get("global_ttl", state.get("ttl_initial", 15)))
        if ttl <= 0:
            return {
                "wave_step_ids": [step_id],
                "step_results": [
                    {
                        "step_id": step_id,
                        "action_id": str(step.get("action_id", "")),
                        "status": "skipped_ttl_exhausted",
                    }
                ],
                "errors": [f"execute_step:{step_id}:ttl_exhausted"],
            }

        action_id = str(step.get("action_id", "listen_only")).strip() or "listen_only"
        context_patch, action_row, action_errors = _execute_action_step(state, deps, step)
        result = {
            "step_id": step_id,
            "action_id": action_id,
            "status": "completed" if action_row is not None else ("skipped" if step.get("can_skip", False) else "failed"),
        }
        patch = {
            "wave_step_ids": [step_id],
            "step_results": [result],
            "wave_context_patches": [context_patch],
        }
        if action_row is not None:
            if action_row.get("action_result") is not None:
                patch["action_results"] = [action_row["action_result"]]
            if action_row.get("event") is not None:
                patch["emitted_events"] = [action_row["event"]]
        if action_errors:
            patch["errors"] = action_errors
        return patch

    def merge_wave_node(state: ActionParallelState) -> ActionParallelState:
        executed = [str(item) for item in state.get("executed_step_ids", [])]
        seen = set(executed)
        wave_step_ids = [str(item) for item in state.get("wave_step_ids", []) if str(item).strip()]
        new_ids = [item for item in wave_step_ids if item not in seen]
        executed.extend(new_ids)

        ttl = int(state.get("global_ttl", state.get("ttl_initial", 15)))
        ttl = max(0, ttl - len(new_ids))

        skill_context = dict(state.get("skill_context", {}))
        for patch in state.get("wave_context_patches", []):
            if not isinstance(patch, dict):
                continue
            for key, value in patch.items():
                if value in (None, [], {}):
                    continue
                skill_context[key] = value

        out: ActionParallelState = {
            "executed_step_ids": executed,
            "global_ttl": ttl,
            "skill_context": skill_context,
            "wave_step_ids": [],
            "wave_context_patches": [],
            "ready_steps": [],
        }
        if ttl <= 0:
            out["errors"] = ["execute_plan: ttl_exhausted_before_plan_complete"]
        return out

    def post_merge_router(state: ActionParallelState) -> str:
        if int(state.get("global_ttl", 0)) <= 0:
            return "finalize_plan"
        steps = [item for item in state.get("plan_steps", []) if isinstance(item, dict)]
        executed = {str(item) for item in state.get("executed_step_ids", [])}
        remaining = [item for item in steps if str(item.get("step_id", "")) not in executed]
        return "finalize_plan" if not remaining else "select_ready_steps"

    def finalize_plan_node(state: ActionParallelState) -> ActionParallelState:
        action_results = _sort_steps(list(state.get("action_results", [])))
        plan_steps = _sort_steps(list(state.get("plan_steps", [])))
        executed = [str(item) for item in state.get("executed_step_ids", []) if str(item).strip()]
        executed_set = set(executed)
        remaining = [str(item.get("step_id", "")) for item in plan_steps if str(item.get("step_id", "")) not in executed_set]
        report = {
            "total_steps": len(plan_steps),
            "executed_steps": len(executed_set),
            "remaining_steps": remaining,
            "completed": len(remaining) == 0,
            "ttl_after_execution": int(state.get("global_ttl", 0)),
            "step_results": list(state.get("step_results", [])),
        }
        out: ActionParallelState = {}
        if action_results:
            primary = action_results[0]
            out["planned_action"] = str(primary.get("action_id", "listen_only"))
            out["action_payload"] = _ensure_payload_scope(primary.get("payload", {}))
        else:
            out["planned_action"] = "listen_only"
            out["action_payload"] = {"reason": "no_executable_action", "world_scope": "group:main"}

        skill_context = dict(state.get("skill_context", {}))
        for key in [
            "focus_reference",
            "support_references",
            "retrieval_channel",
            "retrieval_channels",
            "candidates",
            "reroute_hint",
            "retrieval_trace",
        ]:
            if key in skill_context:
                out[key] = skill_context.get(key)
        out["plan_execution_report"] = report
        if not bool(report.get("completed", False)):
            out["errors"] = [f"execute_plan: plan_incomplete remaining={','.join(remaining)}"]
        return out

    graph.add_node("prepare_plan", prepare_plan_node)
    graph.add_edge(START, "prepare_plan")
    if deps.plan_only:
        graph.add_edge("prepare_plan", END)
        return graph.compile()

    graph.add_node("select_ready_steps", select_ready_steps_node)
    graph.add_node("execute_step", execute_step_node)
    graph.add_node("merge_wave", merge_wave_node)
    graph.add_node("finalize_plan", finalize_plan_node)

    graph.add_edge("prepare_plan", "select_ready_steps")
    graph.add_conditional_edges("select_ready_steps", dispatch_ready_router)
    graph.add_edge("execute_step", "merge_wave")
    graph.add_conditional_edges(
        "merge_wave",
        post_merge_router,
        {
            "select_ready_steps": "select_ready_steps",
            "finalize_plan": "finalize_plan",
        },
    )
    graph.add_edge("finalize_plan", END)
    return graph.compile()
