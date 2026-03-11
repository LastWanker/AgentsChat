from __future__ import annotations

from langgraph.graph import START, END, StateGraph

from graphchat.application.state import AgentState


def build_silent_loop_subgraph():
    graph = StateGraph(AgentState)

    def poll_new_events_node(state: AgentState) -> AgentState:
        last_event = state.get("last_event", {})
        text = str(last_event.get("payload", {}).get("text", ""))
        mention_flag = f"@{state.get('agent_id', '')}" in text
        return {"wake_mention": mention_flag}

    def backoff_control_node(state: AgentState) -> AgentState:
        rounds = int(state.get("silent_rounds", 0)) + 1
        return {"silent_rounds": rounds}

    def wake_signal_filter_node(state: AgentState) -> AgentState:
        max_rounds = int(state.get("max_silent_rounds", 3))
        should_wake = bool(state.get("wake_mention", False)) or int(state.get("silent_rounds", 0)) >= max_rounds
        return {"should_wake": should_wake}

    graph.add_node("poll_new_events", poll_new_events_node)
    graph.add_node("backoff_control", backoff_control_node)
    graph.add_node("wake_signal_filter", wake_signal_filter_node)
    graph.add_edge(START, "poll_new_events")
    graph.add_edge("poll_new_events", "backoff_control")
    graph.add_edge("backoff_control", "wake_signal_filter")
    graph.add_edge("wake_signal_filter", END)
    return graph.compile()

