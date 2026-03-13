from __future__ import annotations

from dataclasses import dataclass

from langgraph.graph import START, END, StateGraph

from graphchat.application.guards.action_registry_guard import action_registry_guard_node
from graphchat.application.guards.idempotency_guard import idempotency_guard_node
from graphchat.application.guards.schema_guard import schema_guard_node
from graphchat.application.nodes.agent_nodes import policy_gate_node
from graphchat.application.state import AgentState
from graphchat.domain.models.action_contract import ActionSpec


@dataclass
class GuardrailDeps:
    action_registry: dict[str, ActionSpec]
    idempotency_cache: set[str]


def build_guardrail_subgraph(deps: GuardrailDeps):
    graph = StateGraph(AgentState)

    def ttl_tick_guard_node(state: AgentState) -> AgentState:
        ttl = int(state.get("global_ttl", 0))
        if ttl <= 0:
            return {"global_ttl": 0}
        return {"global_ttl": ttl - 1}

    graph.add_node("ttl_tick_guard", ttl_tick_guard_node)
    graph.add_node("policy_gate", policy_gate_node)
    graph.add_node("schema_guard", schema_guard_node)
    graph.add_node(
        "action_registry_guard",
        lambda state: action_registry_guard_node(state, deps.action_registry),
    )
    graph.add_node(
        "idempotency_guard",
        lambda state: idempotency_guard_node(state, deps.idempotency_cache),
    )

    graph.add_edge(START, "ttl_tick_guard")
    graph.add_edge("ttl_tick_guard", "policy_gate")
    graph.add_edge("policy_gate", "schema_guard")
    graph.add_edge("schema_guard", "action_registry_guard")
    graph.add_edge("action_registry_guard", "idempotency_guard")
    graph.add_edge("idempotency_guard", END)
    return graph.compile()

