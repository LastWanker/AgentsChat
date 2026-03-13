from __future__ import annotations

from langgraph.graph import START, END, StateGraph

from graphchat.application.graphs.subgraphs.silent_loop_subgraph import build_silent_loop_subgraph
from graphchat.application.nodes.agent_nodes import listening_node
from graphchat.application.state import AgentState


def build_listening_subgraph():
    graph = StateGraph(AgentState)
    silent_loop = build_silent_loop_subgraph()
    graph.add_node("listening", listening_node)
    graph.add_node("silent_loop_subgraph", silent_loop)
    graph.add_edge(START, "listening")
    graph.add_edge("listening", "silent_loop_subgraph")
    graph.add_edge("silent_loop_subgraph", END)
    return graph.compile()

