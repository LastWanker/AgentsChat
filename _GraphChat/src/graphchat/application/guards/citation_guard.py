from __future__ import annotations

from graphchat.application.state import AgentState
from graphchat.domain.policies.citation_policy import check_citation_policy


def citation_guard_node(state: AgentState) -> AgentState:
    ok, reason = check_citation_policy(
        citation_policy=state.get("citation_policy", "none"),
        focus_reference=state.get("focus_reference"),
        candidates=state.get("candidates", []),
    )
    if ok:
        return {}
    reroute_hint = str(state.get("reroute_hint") or "defer").strip().lower()
    base_payload = {
        "reason": reason,
        "reroute_hint": reroute_hint,
        "world_scope": state.get("action_payload", {}).get("world_scope", "group:main"),
    }
    if reroute_hint == "web_search":
        action = "search_web"
    elif reroute_hint == "ask_peer":
        action = "ask_agent"
    else:
        action = "listen_only"
    return {
        "planned_action": action,
        "action_payload": base_payload,
        "errors": [f"citation_guard: {reason}; reroute={reroute_hint}; action={action}"],
    }
