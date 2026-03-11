from __future__ import annotations

from langgraph.graph import START, END, StateGraph

from graphchat.application.nodes.world_nodes import (
    WorldNodeDeps,
    collect_agent_outputs_node,
    commit_events_node,
    dispatch_router,
    idle_check_node,
    ingest_events_node,
    publish_updates_node,
    route_scope_node,
    run_agent_node,
    select_runnable_agents_node,
)
from graphchat.application.state import WorldState


def _idle_router(_state: WorldState) -> str:
    return "__end__"


def build_world_graph(deps: WorldNodeDeps, checkpointer):
    graph = StateGraph(WorldState)
    graph.add_node("ingest_events", ingest_events_node)
    graph.add_node("route_scope", lambda state: route_scope_node(state, deps))
    graph.add_node("select_runnable_agents", select_runnable_agents_node)
    graph.add_node("run_agent", lambda state: run_agent_node(state, deps))
    graph.add_node("collect_agent_outputs", collect_agent_outputs_node)
    graph.add_node("commit_events", lambda state: commit_events_node(state, deps))
    graph.add_node("publish_updates", publish_updates_node)
    graph.add_node("idle_check", idle_check_node)

    graph.add_edge(START, "ingest_events")
    graph.add_edge("ingest_events", "route_scope")
    graph.add_edge("route_scope", "select_runnable_agents")
    graph.add_conditional_edges("select_runnable_agents", dispatch_router)
    graph.add_edge("run_agent", "collect_agent_outputs")
    graph.add_edge("collect_agent_outputs", "commit_events")
    graph.add_edge("commit_events", "publish_updates")
    graph.add_edge("publish_updates", "idle_check")
    graph.add_conditional_edges("idle_check", _idle_router, {"__end__": END})

    return graph.compile(checkpointer=checkpointer)
