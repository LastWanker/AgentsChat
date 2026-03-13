from __future__ import annotations

import operator
from typing import TypedDict
from typing_extensions import Annotated

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from graphchat.application.graphs.subgraphs.action_parallel_subgraph import (
    ActionParallelDeps,
    _ensure_payload_scope,
    _execute_action_step,
    _sort_steps,
)
from graphchat.application.skills.guard_profiles import BOARD_ACTIONS, GOVERNANCE_ACTIONS


class SkillExecutionState(TypedDict, total=False):
    session_id: str
    agent_id: str
    visible_events: list[dict]
    last_event: dict
    global_ttl: int
    ttl_initial: int
    enabled_retrieval_channels: list[str]
    planned_actions: list[dict]
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


def _skill_lane(action_id: str) -> str:
    action = str(action_id).strip()
    if action == "rag":
        return "skill_rag"
    if action in BOARD_ACTIONS:
        return "skill_board"
    if action in GOVERNANCE_ACTIONS:
        return "skill_governance"
    if action in {"speak", "ask_agent", "search_web", "request_file", "share_file"}:
        return "skill_dialog"
    return "skill_generic"


def build_skill_execution_subgraph(deps: ActionParallelDeps):
    graph = StateGraph(SkillExecutionState)

    def select_ready_steps_node(state: SkillExecutionState) -> SkillExecutionState:
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
                f"skill_execution: dependency_deadlock_resolved_by_force_step={ready[0].get('step_id', '')}"
            )

        parallel_batch = [item for item in ready if str(item.get("dispatch", "auto")).lower() == "parallel"]
        selected = parallel_batch or [ready[0]]
        patch: SkillExecutionState = {"ready_steps": selected}
        if errors:
            patch["errors"] = errors
        return patch

    def dispatch_ready_router(state: SkillExecutionState):
        ready = [item for item in state.get("ready_steps", []) if isinstance(item, dict)]
        if not ready:
            return "finalize_plan"
        return [
            Send(
                _skill_lane(str(item.get("action_id", "listen_only"))),
                {
                    "session_id": state.get("session_id", ""),
                    "agent_id": state.get("agent_id", ""),
                    "visible_events": list(state.get("visible_events", [])),
                    "last_event": dict(state.get("last_event", {})),
                    "global_ttl": int(state.get("global_ttl", state.get("ttl_initial", 15))),
                    "ttl_initial": int(state.get("ttl_initial", 15)),
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

    def execute_skill_lane_node(state: SkillExecutionState, lane: str) -> SkillExecutionState:
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
                        "skill_lane": lane,
                    }
                ],
                "errors": [f"{lane}:{step_id}:ttl_exhausted"],
            }

        action_id = str(step.get("action_id", "listen_only")).strip() or "listen_only"
        context_patch, action_row, action_errors = _execute_action_step(state, deps, step)
        result = {
            "step_id": step_id,
            "action_id": action_id,
            "status": "completed" if action_row is not None else ("skipped" if step.get("can_skip", False) else "failed"),
            "skill_lane": lane,
        }
        patch: SkillExecutionState = {
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

    def merge_wave_node(state: SkillExecutionState) -> SkillExecutionState:
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

        out: SkillExecutionState = {
            "executed_step_ids": executed,
            "global_ttl": ttl,
            "skill_context": skill_context,
            "wave_step_ids": [],
            "wave_context_patches": [],
            "ready_steps": [],
        }
        if ttl <= 0:
            out["errors"] = ["skill_execution: ttl_exhausted_before_plan_complete"]
        return out

    def post_merge_router(state: SkillExecutionState) -> str:
        if int(state.get("global_ttl", 0)) <= 0:
            return "finalize_plan"
        steps = [item for item in state.get("plan_steps", []) if isinstance(item, dict)]
        executed = {str(item) for item in state.get("executed_step_ids", [])}
        remaining = [item for item in steps if str(item.get("step_id", "")) not in executed]
        return "finalize_plan" if not remaining else "select_ready_steps"

    def finalize_plan_node(state: SkillExecutionState) -> SkillExecutionState:
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
        out: SkillExecutionState = {}
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
            out["errors"] = [f"skill_execution: plan_incomplete remaining={','.join(remaining)}"]
        return out

    graph.add_node("select_ready_steps", select_ready_steps_node)
    graph.add_node("skill_rag", lambda state: execute_skill_lane_node(state, "skill_rag"))
    graph.add_node("skill_board", lambda state: execute_skill_lane_node(state, "skill_board"))
    graph.add_node("skill_governance", lambda state: execute_skill_lane_node(state, "skill_governance"))
    graph.add_node("skill_dialog", lambda state: execute_skill_lane_node(state, "skill_dialog"))
    graph.add_node("skill_generic", lambda state: execute_skill_lane_node(state, "skill_generic"))
    graph.add_node("merge_wave", merge_wave_node)
    graph.add_node("finalize_plan", finalize_plan_node)

    graph.add_edge(START, "select_ready_steps")
    graph.add_conditional_edges("select_ready_steps", dispatch_ready_router)
    graph.add_edge("skill_rag", "merge_wave")
    graph.add_edge("skill_board", "merge_wave")
    graph.add_edge("skill_governance", "merge_wave")
    graph.add_edge("skill_dialog", "merge_wave")
    graph.add_edge("skill_generic", "merge_wave")
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
