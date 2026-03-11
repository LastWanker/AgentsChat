from __future__ import annotations

from langgraph.graph import START, END, StateGraph

from graphchat.application.state import AgentState


def build_governance_subgraph():
    graph = StateGraph(AgentState)

    def governance_prepare_node(state: AgentState) -> AgentState:
        action = state.get("planned_action", "")
        payload = dict(state.get("action_payload", {}))

        if action == "vote_decision":
            payload.setdefault("vote", {"status": "opened", "options": ["yes", "no"]})
        elif action == "dissolve_group":
            payload.setdefault("reason", "pending_reason")
            payload.setdefault("needs_boss_review", True)
        # 待拓展：这里预留了群治理动作聚合点，后续可以扩展 transfer_group_owner 等动作。
        return {"action_payload": payload}

    graph.add_node("governance_prepare", governance_prepare_node)
    graph.add_edge(START, "governance_prepare")
    graph.add_edge("governance_prepare", END)
    return graph.compile()

