from __future__ import annotations

from dataclasses import dataclass, field

from langgraph.graph import START, END, StateGraph

from graphchat.application.state import AgentState
from graphchat.infrastructure.retrieval.channels import (
    RetrievalContext,
    SearchProvider,
    build_default_channels,
)
from graphchat.infrastructure.retrieval.fusion import merge_and_rank_candidates
from graphchat.infrastructure.retrieval.tag_index import TagInvertedIndex
from graphchat.infrastructure.retrieval.vector_index import VectorIndex


@dataclass
class RetrievalDeps:
    tag_index: TagInvertedIndex
    vector_index: VectorIndex
    enabled_channels: set[str] = field(
        default_factory=lambda: {"world_history", "ask_peer", "file_search", "web_search"}
    )
    peer_search_provider: SearchProvider | None = None
    web_search_provider: SearchProvider | None = None
    file_search_provider: SearchProvider | None = None


def _default_channel_plan(action: str) -> list[str]:
    if action in {"search_web"}:
        return ["web_search", "world_history", "ask_peer"]
    if action in {"request_file", "share_file"}:
        return ["file_search", "world_history", "ask_peer"]
    if action in {"vote_decision", "assign_task", "maintain_board"}:
        return ["world_history", "ask_peer", "file_search"]
    return ["world_history", "ask_peer"]


def build_retrieval_subgraph(deps: RetrievalDeps):
    graph = StateGraph(AgentState)
    channels = build_default_channels(
        tag_index=deps.tag_index,
        vector_index=deps.vector_index,
        peer_provider=deps.peer_search_provider,
        web_provider=deps.web_search_provider,
        file_provider=deps.file_search_provider,
    )

    def choose_channel_node(state: AgentState) -> AgentState:
        action = str(state.get("planned_action", ""))
        requested = _default_channel_plan(action)
        enabled = deps.enabled_channels or set(channels.keys())
        selected = [ch for ch in requested if ch in enabled and ch in channels]
        if not selected and "world_history" in channels:
            selected = ["world_history"]
        return {
            "retrieval_channel": selected[0] if selected else "world_history",
            "retrieval_channels": selected,
            "retrieval_trace": {
                "action": action,
                "requested_channels": requested,
                "enabled_channels": sorted(enabled),
                "selected_channels": selected,
            },
        }

    def retrieve_candidates_node(state: AgentState) -> AgentState:
        query = str(
            state.get("action_payload", {}).get("text")
            or state.get("last_event", {}).get("payload", {}).get("text", "")
        )
        selected_channels = list(state.get("retrieval_channels", []))
        ctx = RetrievalContext(
            session_id=str(state.get("session_id", "")),
            agent_id=str(state.get("agent_id", "")),
            query=query,
            visible_events=list(state.get("visible_events", [])),
        )

        raw_candidates: list[dict] = []
        channel_hits: dict[str, int] = {}
        channel_errors: dict[str, str] = {}
        for channel_id in selected_channels:
            ch = channels.get(channel_id)
            if ch is None:
                continue
            try:
                items = ch.retrieve(ctx, top_k=5)
            except Exception as exc:
                channel_errors[channel_id] = str(exc)
                continue
            channel_hits[channel_id] = len(items)
            raw_candidates.extend(items)

        retrieval_trace = dict(state.get("retrieval_trace", {}))
        retrieval_trace["query"] = query
        retrieval_trace["channel_hits"] = channel_hits
        if channel_errors:
            retrieval_trace["channel_errors"] = channel_errors
        retrieval_trace["raw_candidate_count"] = len(raw_candidates)
        return {"candidates": raw_candidates, "retrieval_trace": retrieval_trace}

    def rank_candidates_node(state: AgentState) -> AgentState:
        selected_channels = list(state.get("retrieval_channels", []))
        candidates = merge_and_rank_candidates(
            raw_candidates=list(state.get("candidates", [])),
            total_channels=len(selected_channels),
            top_k=8,
        )
        focus = candidates[0]["event_id"] if candidates else None
        support = [item["event_id"] for item in candidates[1:3] if item.get("event_id")]
        reroute_hint = None
        if not candidates:
            reroute_hint = "ask_peer" if "ask_peer" in selected_channels else "defer"

        retrieval_trace = dict(state.get("retrieval_trace", {}))
        retrieval_trace["ranked_candidate_count"] = len(candidates)
        retrieval_trace["focus_reference"] = focus
        retrieval_trace["support_references"] = support
        if reroute_hint:
            retrieval_trace["reroute_hint"] = reroute_hint

        return {
            "candidates": candidates,
            "focus_reference": focus,
            "support_references": support,
            "reroute_hint": reroute_hint,
            "retrieval_trace": retrieval_trace,
        }

    graph.add_node("choose_channel", choose_channel_node)
    graph.add_node("retrieve_candidates", retrieve_candidates_node)
    graph.add_node("rank_candidates", rank_candidates_node)
    graph.add_edge(START, "choose_channel")
    graph.add_edge("choose_channel", "retrieve_candidates")
    graph.add_edge("retrieve_candidates", "rank_candidates")
    graph.add_edge("rank_candidates", END)
    return graph.compile()
