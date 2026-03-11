from __future__ import annotations

from graphchat.application.state import AgentState
from graphchat.domain.models.schemas import validate_agent_plan


def schema_guard_node(state: AgentState) -> AgentState:
    action = state.get("planned_action")
    payload = state.get("action_payload")
    citation_policy = state.get("citation_policy", "none")

    if not action:
        return {
            "planned_action": "listen_only",
            "action_payload": {"reason": "schema_guard_missing_action"},
            "errors": ["schema_guard: missing planned_action"],
        }
    if payload is None:
        payload = {}

    parsed, err = validate_agent_plan(
        planned_action=action,
        action_payload=payload,
        citation_policy=citation_policy,
    )
    if err:
        return {
            "planned_action": "listen_only",
            "action_payload": {"reason": "schema_guard_invalid_plan"},
            "citation_policy": "none",
            "errors": [f"schema_guard: {err}"],
        }

    return {
        "planned_action": parsed["planned_action"],
        "action_payload": parsed["action_payload"],
        "citation_policy": parsed["citation_policy"],
    }
