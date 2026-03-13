from __future__ import annotations

from graphchat.application.graphs.subgraphs.action_parallel_subgraph import (
    ActionParallelDeps,
    build_action_parallel_subgraph,
)
from graphchat.application.graphs.subgraphs.board_subgraph import BoardDeps, build_board_subgraph
from graphchat.application.graphs.subgraphs.governance_subgraph import build_governance_subgraph
from graphchat.application.graphs.subgraphs.retrieval_subgraph import RetrievalDeps, build_retrieval_subgraph
from graphchat.application.skills.guard_profiles import build_default_skill_profiles
from graphchat.domain.models.action_contract import default_action_registry
from graphchat.infrastructure.persistence.board_store import BoardStore
from graphchat.infrastructure.retrieval.tag_index import TagInvertedIndex
from graphchat.infrastructure.retrieval.vector_index import VectorIndex


def test_action_parallel_subgraph_should_execute_step_plan_and_emit_events(tmp_path) -> None:
    registry = default_action_registry()
    retrieval = build_retrieval_subgraph(
        RetrievalDeps(
            tag_index=TagInvertedIndex(),
            vector_index=VectorIndex(),
            enabled_channels={"world_history", "ask_peer", "web_search", "file_search"},
        )
    )
    board = build_board_subgraph(BoardDeps(board_store=BoardStore(tmp_path / "sessions")))
    governance = build_governance_subgraph()
    graph = build_action_parallel_subgraph(
        ActionParallelDeps(
            allowed_actions=set(registry.keys()) | {"rag"},
            action_registry=registry,
            skill_profiles=build_default_skill_profiles(registry),
            idempotency_cache=set(),
            retrieval_subgraph=retrieval,
            board_subgraph=board,
            governance_subgraph=governance,
        )
    )
    state = {
        "session_id": "s1",
        "agent_id": "agent_1",
        "visible_events": [{"event_id": "e1", "payload": {"text": "hello"}, "world_scope": "group:main"}],
        "last_event": {"event_id": "e1", "payload": {"text": "hello"}},
        "global_ttl": 8,
        "planned_actions": [
            {
                "step_id": "s1",
                "action_id": "rag",
                "plan_text": "先检索",
                "payload": {"query": "hello", "for_action": "search_web", "world_scope": "group:main"},
                "target_scope": "group:main",
                "target_agents": [],
                "depends_on": [],
                "dispatch": "serial",
                "priority": 5,
                "can_skip": False,
                "step_index": 1,
            },
            {
                "step_id": "s2",
                "action_id": "speak",
                "plan_text": "再发言",
                "payload": {"text": "done", "world_scope": "group:main"},
                "target_scope": "group:main",
                "target_agents": [],
                "depends_on": ["s1"],
                "dispatch": "serial",
                "priority": 20,
                "can_skip": False,
                "step_index": 2,
            },
        ],
    }
    result = graph.invoke(state)
    assert len(result.get("step_results", [])) >= 2
    assert len(result.get("action_results", [])) == 1
    assert result.get("action_results", [])[0].get("action_id") == "speak"
    assert len(result.get("emitted_events", [])) == 1
    assert result.get("global_ttl") == 6
    assert result.get("plan_execution_report", {}).get("completed") is True


def test_action_parallel_subgraph_should_support_plan_only_mode(tmp_path) -> None:
    registry = default_action_registry()
    retrieval = build_retrieval_subgraph(
        RetrievalDeps(
            tag_index=TagInvertedIndex(),
            vector_index=VectorIndex(),
            enabled_channels={"world_history", "ask_peer", "web_search", "file_search"},
        )
    )
    board = build_board_subgraph(BoardDeps(board_store=BoardStore(tmp_path / "sessions")))
    governance = build_governance_subgraph()
    graph = build_action_parallel_subgraph(
        ActionParallelDeps(
            allowed_actions=set(registry.keys()) | {"rag"},
            action_registry=registry,
            skill_profiles=build_default_skill_profiles(registry),
            idempotency_cache=set(),
            retrieval_subgraph=retrieval,
            board_subgraph=board,
            governance_subgraph=governance,
            plan_only=True,
        )
    )
    result = graph.invoke(
        {
            "session_id": "s_plan_only",
            "agent_id": "agent_1",
            "planned_actions": [
                {
                    "step_id": "s1",
                    "action_id": "speak",
                    "plan_text": "plan only",
                    "payload": {"text": "hello", "world_scope": "group:main"},
                    "target_scope": "group:main",
                    "target_agents": [],
                    "depends_on": [],
                    "dispatch": "serial",
                    "priority": 10,
                    "can_skip": False,
                    "step_index": 1,
                }
            ],
        }
    )
    assert len(result.get("plan_steps", [])) == 1
    assert result.get("executed_step_ids", []) == []
    assert result.get("action_results", []) == []
    assert result.get("emitted_events", []) == []
    assert result.get("plan_execution_report", {}) == {}
