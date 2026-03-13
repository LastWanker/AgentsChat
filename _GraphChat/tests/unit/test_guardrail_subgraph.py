from __future__ import annotations

from graphchat.application.graphs.subgraphs.guardrail_subgraph import GuardrailDeps, build_guardrail_subgraph
from graphchat.domain.models.action_contract import default_action_registry


def test_guardrail_subgraph_should_tick_ttl_and_pass_valid_action() -> None:
    deps = GuardrailDeps(
        action_registry=default_action_registry(),
        idempotency_cache=set(),
    )
    graph = build_guardrail_subgraph(deps)
    state = {
        "global_ttl": 5,
        "planned_action": "speak",
        "action_payload": {"text": "hello", "world_scope": "group:main"},
        "citation_policy": "optional",
        "idempotency_key": "k1",
    }
    result = graph.invoke(state)
    assert result.get("global_ttl") == 4
    assert result.get("planned_action") == "speak"


def test_guardrail_subgraph_should_reject_duplicate_idempotency_key() -> None:
    seen = {"k_dup"}
    deps = GuardrailDeps(
        action_registry=default_action_registry(),
        idempotency_cache=seen,
    )
    graph = build_guardrail_subgraph(deps)
    state = {
        "global_ttl": 3,
        "planned_action": "speak",
        "action_payload": {"text": "x", "world_scope": "group:main"},
        "citation_policy": "optional",
        "idempotency_key": "k_dup",
    }
    result = graph.invoke(state)
    assert result.get("planned_action") == "listen_only"
    assert any("idempotency_guard" in err for err in result.get("errors", []))
