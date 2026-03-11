from __future__ import annotations

from graphchat.application.graphs.subgraphs.retrieval_subgraph import RetrievalDeps, build_retrieval_subgraph
from graphchat.infrastructure.retrieval.channels import SearchProvider
from graphchat.infrastructure.retrieval.tag_index import TagInvertedIndex
from graphchat.infrastructure.retrieval.vector_index import VectorIndex


def test_retrieval_channel_switch_should_fallback_to_enabled_world_history() -> None:
    deps = RetrievalDeps(
        tag_index=TagInvertedIndex(),
        vector_index=VectorIndex(),
        enabled_channels={"world_history"},
    )
    graph = build_retrieval_subgraph(deps)
    state = {
        "session_id": "s_retrieval",
        "agent_id": "agent_1",
        "planned_action": "search_web",
        "action_payload": {"text": "查一下项目状态"},
        "visible_events": [
            {"event_id": "e1", "payload": {"text": "项目状态：进行中"}, "actor_id": "agent_2"},
            {"event_id": "e2", "payload": {"text": "风险：接口超时"}, "actor_id": "agent_3"},
        ],
    }

    result = graph.invoke(state)
    assert result.get("retrieval_channel") == "world_history"
    assert result.get("retrieval_channels") == ["world_history"]
    assert result.get("retrieval_trace", {}).get("selected_channels") == ["world_history"]
    assert isinstance(result.get("candidates"), list)


def test_retrieval_no_candidates_should_emit_reroute_hint() -> None:
    deps = RetrievalDeps(
        tag_index=TagInvertedIndex(),
        vector_index=VectorIndex(),
        enabled_channels={"file_search"},
    )
    graph = build_retrieval_subgraph(deps)
    state = {
        "session_id": "s_retrieval_empty",
        "agent_id": "agent_1",
        "planned_action": "request_file",
        "action_payload": {"text": "给我文档"},
        "visible_events": [],
    }

    result = graph.invoke(state)
    assert result.get("candidates") == []
    assert result.get("reroute_hint") == "defer"


class _ExplodingWebProvider(SearchProvider):
    def search(
        self,
        *,
        session_id: str,
        query: str,
        top_k: int,
        agent_id: str | None = None,
        visible_events: list[dict] | None = None,
    ) -> list[dict]:
        del session_id, query, top_k, agent_id, visible_events
        raise RuntimeError("network down")


def test_retrieval_channel_failure_should_not_break_main_flow() -> None:
    deps = RetrievalDeps(
        tag_index=TagInvertedIndex(),
        vector_index=VectorIndex(),
        enabled_channels={"web_search", "world_history"},
        web_search_provider=_ExplodingWebProvider(),
    )
    graph = build_retrieval_subgraph(deps)
    state = {
        "session_id": "s_retrieval_err",
        "agent_id": "agent_1",
        "planned_action": "search_web",
        "action_payload": {"text": "查项目状态"},
        "visible_events": [{"event_id": "e1", "payload": {"text": "状态同步"}, "actor_id": "agent_2"}],
    }
    result = graph.invoke(state)
    trace = result.get("retrieval_trace", {})
    assert trace.get("channel_errors", {}).get("web_search") == "network down"
    assert isinstance(result.get("candidates"), list)
