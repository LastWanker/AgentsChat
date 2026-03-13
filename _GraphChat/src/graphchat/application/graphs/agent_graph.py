from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from graphchat.application.graphs.subgraphs.action_parallel_subgraph import (
    ActionParallelDeps,
    build_action_parallel_subgraph,
)
from graphchat.application.graphs.subgraphs.board_subgraph import BoardDeps, build_board_subgraph
from graphchat.application.graphs.subgraphs.governance_subgraph import build_governance_subgraph
from graphchat.application.graphs.subgraphs.listening_subgraph import build_listening_subgraph
from graphchat.application.graphs.subgraphs.retrieval_subgraph import RetrievalDeps, build_retrieval_subgraph
from graphchat.application.graphs.subgraphs.skill_execution_subgraph import build_skill_execution_subgraph
from graphchat.application.nodes.agent_nodes import (
    AgentNodeDeps,
    decide_wake_node,
    decide_wake_router,
    lifecycle_gate_node,
    lifecycle_router,
    plan_action_node,
)
from graphchat.application.skills.guard_profiles import SkillGuardProfile
from graphchat.application.state import AgentState


def build_agent_graph(
    deps: AgentNodeDeps,
    retrieval_deps: RetrievalDeps,
    board_deps: BoardDeps,
    skill_profiles: dict[str, SkillGuardProfile],
    checkpointer,
):
    graph = StateGraph(AgentState)

    listening_subgraph = build_listening_subgraph()
    retrieval_subgraph = build_retrieval_subgraph(retrieval_deps)
    board_subgraph = build_board_subgraph(board_deps)
    governance_subgraph = build_governance_subgraph()
    action_parallel_subgraph = build_action_parallel_subgraph(
        ActionParallelDeps(
            allowed_actions=set(deps.action_registry.keys()) | {"rag"},
            action_registry=deps.action_registry,
            skill_profiles=skill_profiles,
            idempotency_cache=deps.idempotency_cache,
            retrieval_subgraph=retrieval_subgraph,
            board_subgraph=board_subgraph,
            governance_subgraph=governance_subgraph,
            plan_only=True,
        )
    )
    skill_execution_subgraph = build_skill_execution_subgraph(
        ActionParallelDeps(
            allowed_actions=set(deps.action_registry.keys()) | {"rag"},
            action_registry=deps.action_registry,
            skill_profiles=skill_profiles,
            idempotency_cache=deps.idempotency_cache,
            retrieval_subgraph=retrieval_subgraph,
            board_subgraph=board_subgraph,
            governance_subgraph=governance_subgraph,
        )
    )

    graph.add_node("listening_subgraph", listening_subgraph)
    graph.add_node("decide_wake", decide_wake_node)
    graph.add_node("plan_action", lambda state: plan_action_node(state, deps))
    # Planner-Executor: planning and execution are explicit sequential nodes.
    graph.add_node("action_parallel_subgraph", action_parallel_subgraph)
    graph.add_node("skill_execution_subgraph", skill_execution_subgraph)
    graph.add_node("lifecycle_gate", lifecycle_gate_node)

    graph.add_edge(START, "listening_subgraph")
    graph.add_edge("listening_subgraph", "decide_wake")
    graph.add_conditional_edges("decide_wake", decide_wake_router, {"plan_action": "plan_action", "__end__": END})
    graph.add_edge("plan_action", "action_parallel_subgraph")
    graph.add_edge("action_parallel_subgraph", "skill_execution_subgraph")
    graph.add_edge("skill_execution_subgraph", "lifecycle_gate")
    graph.add_conditional_edges(
        "lifecycle_gate",
        lifecycle_router,
        {
            "listening_subgraph": "listening_subgraph",
            "decide_wake": "decide_wake",
            "__end__": END,
        },
    )

    return graph.compile(checkpointer=checkpointer)
