from __future__ import annotations

from dataclasses import replace

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


def test_skill_guard_profile_should_allow_context_only_step(tmp_path) -> None:
    registry = default_action_registry()
    profiles = build_default_skill_profiles(registry)
    profiles["speak"] = replace(profiles["speak"], emit_event=False, enable_idempotency_guard=False)

    graph = build_action_parallel_subgraph(
        ActionParallelDeps(
            allowed_actions=set(registry.keys()) | {"rag"},
            action_registry=registry,
            skill_profiles=profiles,
            idempotency_cache=set(),
            retrieval_subgraph=build_retrieval_subgraph(
                RetrievalDeps(
                    tag_index=TagInvertedIndex(),
                    vector_index=VectorIndex(),
                )
            ),
            board_subgraph=build_board_subgraph(BoardDeps(board_store=BoardStore(tmp_path / "sessions"))),
            governance_subgraph=build_governance_subgraph(),
        )
    )
    out = graph.invoke(
        {
            "session_id": "s_profile",
            "agent_id": "agent_1",
            "visible_events": [{"event_id": "e1", "payload": {"text": "x"}}],
            "last_event": {"event_id": "e1", "payload": {"text": "x"}},
            "global_ttl": 4,
            "planned_actions": [
                {
                    "step_id": "s1",
                    "action_id": "speak",
                    "plan_text": "context only",
                    "payload": {"text": "hello", "world_scope": "group:main"},
                    "target_scope": "group:main",
                    "target_agents": [],
                    "depends_on": [],
                    "dispatch": "serial",
                    "priority": 20,
                    "can_skip": False,
                    "step_index": 1,
                }
            ],
        }
    )
    assert out.get("action_results", []) == []
    assert out.get("step_results", [])[0].get("status") == "completed"
    assert out.get("emitted_events", []) == []
