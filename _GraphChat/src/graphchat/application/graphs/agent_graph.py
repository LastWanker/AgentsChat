from __future__ import annotations

from langgraph.graph import START, END, StateGraph

from graphchat.application.guards.action_registry_guard import action_registry_guard_node
from graphchat.application.guards.citation_guard import citation_guard_node
from graphchat.application.guards.idempotency_guard import idempotency_guard_node
from graphchat.application.guards.schema_guard import schema_guard_node
from graphchat.application.graphs.subgraphs.board_subgraph import BoardDeps, build_board_subgraph
from graphchat.application.graphs.subgraphs.governance_subgraph import build_governance_subgraph
from graphchat.application.graphs.subgraphs.retrieval_subgraph import RetrievalDeps, build_retrieval_subgraph
from graphchat.application.graphs.subgraphs.silent_loop_subgraph import build_silent_loop_subgraph
from graphchat.application.nodes.agent_nodes import (
    AgentNodeDeps,
    decide_wake_node,
    decide_wake_router,
    emit_event_node,
    listening_node,
    plan_action_node,
    policy_gate_node,
    retrieval_router,
)
from graphchat.application.state import AgentState


def build_agent_graph(
    deps: AgentNodeDeps,
    retrieval_deps: RetrievalDeps,
    board_deps: BoardDeps,
    checkpointer,
):
    graph = StateGraph(AgentState)

    silent_loop = build_silent_loop_subgraph()
    retrieval_subgraph = build_retrieval_subgraph(retrieval_deps)
    board_subgraph = build_board_subgraph(board_deps)
    governance_subgraph = build_governance_subgraph()

    graph.add_node("listening", listening_node)
    # 官方子图能力：直接把已编译子图挂到父图节点。
    graph.add_node("silent_loop_subgraph", silent_loop)
    graph.add_node("decide_wake", decide_wake_node)
    graph.add_node("plan_action", lambda state: plan_action_node(state, deps))
    graph.add_node("retrieval_subgraph", retrieval_subgraph)
    graph.add_node("citation_guard", citation_guard_node)
    graph.add_node("board_subgraph", board_subgraph)
    graph.add_node("governance_subgraph", governance_subgraph)
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
    graph.add_node("emit_event", lambda state: emit_event_node(state, deps))

    graph.add_edge(START, "listening")
    graph.add_edge("listening", "silent_loop_subgraph")
    graph.add_edge("silent_loop_subgraph", "decide_wake")
    graph.add_conditional_edges("decide_wake", decide_wake_router, {"plan_action": "plan_action", "__end__": END})
    graph.add_conditional_edges(
        "plan_action",
        retrieval_router,
        {"retrieval_subgraph": "retrieval_subgraph", "citation_guard": "citation_guard"},
    )
    graph.add_edge("retrieval_subgraph", "citation_guard")
    graph.add_edge("citation_guard", "board_subgraph")
    graph.add_edge("board_subgraph", "governance_subgraph")
    graph.add_edge("governance_subgraph", "policy_gate")
    graph.add_edge("policy_gate", "schema_guard")
    graph.add_edge("schema_guard", "action_registry_guard")
    graph.add_edge("action_registry_guard", "idempotency_guard")
    graph.add_edge("idempotency_guard", "emit_event")
    graph.add_edge("emit_event", END)

    return graph.compile(checkpointer=checkpointer)

