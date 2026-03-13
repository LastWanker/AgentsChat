from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from graphchat.application.nodes.world_nodes import (
    WorldNodeDeps,
    broker_mentions_and_replies_node,
    collect_agent_outputs_node,
    commit_events_node,
    dispatch_router,
    ingest_events_node,
    ingest_world_commands_node,
    publish_updates_node,
    refresh_registry_and_scope_node,
    route_scope_node,
    run_agent_node,
    schedule_agent_tasks_node,
    world_loop_gate_node,
    world_loop_router,
)
from graphchat.application.state import WorldState


def build_world_graph(deps: WorldNodeDeps, checkpointer):
    graph = StateGraph(WorldState)
    graph.add_node("ingest_world_commands", lambda state: ingest_world_commands_node(state, deps))
    graph.add_node("ingest_events", ingest_events_node)
    graph.add_node("refresh_registry_and_scope", lambda state: refresh_registry_and_scope_node(state, deps))
    graph.add_node("route_scope", lambda state: route_scope_node(state, deps))
    graph.add_node("schedule_agent_tasks", lambda state: schedule_agent_tasks_node(state, deps))
    graph.add_node("run_agent", lambda state: run_agent_node(state, deps))
    graph.add_node("collect_agent_outputs", collect_agent_outputs_node)
    graph.add_node("broker_mentions_and_replies", lambda state: broker_mentions_and_replies_node(state, deps))
    graph.add_node("commit_events", lambda state: commit_events_node(state, deps))
    graph.add_node("publish_updates", publish_updates_node)
    graph.add_node("world_loop_gate", world_loop_gate_node)

    graph.add_edge(START, "ingest_world_commands")
    graph.add_edge("ingest_world_commands", "ingest_events")
    graph.add_edge("ingest_events", "refresh_registry_and_scope")
    graph.add_edge("refresh_registry_and_scope", "route_scope")
    graph.add_edge("route_scope", "schedule_agent_tasks")
    graph.add_conditional_edges("schedule_agent_tasks", dispatch_router)
    graph.add_edge("run_agent", "collect_agent_outputs")
    graph.add_edge("collect_agent_outputs", "broker_mentions_and_replies")
    graph.add_edge("broker_mentions_and_replies", "commit_events")
    graph.add_edge("commit_events", "publish_updates")
    graph.add_edge("publish_updates", "world_loop_gate")
    graph.add_conditional_edges(
        "world_loop_gate",
        world_loop_router,
        {
            "ingest_world_commands": "ingest_world_commands",
            "__end__": END,
        },
    )

    return graph.compile(checkpointer=checkpointer)

