from __future__ import annotations

from graphchat.application.state import AgentState


def idempotency_guard_node(state: AgentState, seen_keys: set[str]) -> AgentState:
    key = state.get("idempotency_key")
    if not key:
        return {}
    if key in seen_keys:
        return {
            "planned_action": "listen_only",
            "action_payload": {"reason": "idempotent_skip"},
            "errors": [f"idempotency_guard: duplicated {key}"],
        }
    # 待拓展：这里只做预检，真正写入幂等锁在副作用节点内完成（避免提前占位）。
    return {}
