from __future__ import annotations

from graphchat.application.graphs.subgraphs.action_parallel_subgraph import ActionParallelDeps
from graphchat.application.graphs.subgraphs.board_subgraph import BoardDeps, build_board_subgraph
from graphchat.application.graphs.subgraphs.governance_subgraph import build_governance_subgraph
from graphchat.application.graphs.subgraphs.retrieval_subgraph import RetrievalDeps, build_retrieval_subgraph
from graphchat.application.graphs.subgraphs.skill_execution_subgraph import build_skill_execution_subgraph
from graphchat.application.skills.guard_profiles import build_default_skill_profiles
from graphchat.domain.models.action_contract import default_action_registry
from graphchat.infrastructure.persistence.board_store import BoardStore
from graphchat.infrastructure.retrieval.tag_index import TagInvertedIndex
from graphchat.infrastructure.retrieval.vector_index import VectorIndex


def test_skill_execution_subgraph_should_execute_planned_steps(tmp_path) -> None:
    registry = default_action_registry()
    graph = build_skill_execution_subgraph(
        ActionParallelDeps(
            allowed_actions=set(registry.keys()) | {"rag"},
            action_registry=registry,
            skill_profiles=build_default_skill_profiles(registry),
            idempotency_cache=set(),
            retrieval_subgraph=build_retrieval_subgraph(
                RetrievalDeps(
                    tag_index=TagInvertedIndex(),
                    vector_index=VectorIndex(),
                    enabled_channels={"world_history", "ask_peer", "web_search", "file_search"},
                )
            ),
            board_subgraph=build_board_subgraph(BoardDeps(board_store=BoardStore(tmp_path / "sessions"))),
            governance_subgraph=build_governance_subgraph(),
        )
    )
    out = graph.invoke(
        {
            "session_id": "s_exec",
            "agent_id": "agent_1",
            "visible_events": [{"event_id": "e1", "payload": {"text": "hello"}, "world_scope": "group:main"}],
            "last_event": {"event_id": "e1", "payload": {"text": "hello"}},
            "global_ttl": 8,
            "ttl_initial": 8,
            "plan_steps": [
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
            "executed_step_ids": [],
            "skill_context": {},
            "step_results": [],
            "wave_step_ids": [],
            "wave_context_patches": [],
            "action_results": [],
            "emitted_events": [],
            "errors": [],
        }
    )
    assert len(out.get("step_results", [])) >= 2
    assert any(item.get("skill_lane") == "skill_rag" for item in out.get("step_results", []))
    assert len(out.get("action_results", [])) == 1
    assert out.get("action_results", [])[0].get("action_id") == "speak"
    assert len(out.get("emitted_events", [])) == 1
    assert out.get("plan_execution_report", {}).get("completed") is True
