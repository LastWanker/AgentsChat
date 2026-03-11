from __future__ import annotations

from graphchat.application.state import AgentState
from graphchat.domain.models.action_contract import ActionSpec


def action_registry_guard_node(state: AgentState, registry: dict[str, ActionSpec]) -> AgentState:
    action = state.get("planned_action", "")
    spec = registry.get(action)
    if spec and spec.enabled:
        return {}
    # 待拓展：这里可接入更精细的权限系统（角色、组、资源级授权）。
    return {
        "planned_action": "listen_only",
        "action_payload": {"reason": f"action_disabled_or_missing:{action}"},
        "errors": [f"action_registry_guard: reject {action}"],
    }

