from __future__ import annotations

from graphchat.application.guards.citation_guard import citation_guard_node


def test_citation_guard_should_reroute_by_hint() -> None:
    state = {
        "citation_policy": "required_focus",
        "focus_reference": None,
        "candidates": [],
        "reroute_hint": "web_search",
        "action_payload": {"world_scope": "group:main"},
    }
    result = citation_guard_node(state)
    assert result.get("planned_action") == "search_web"
    assert result.get("action_payload", {}).get("reroute_hint") == "web_search"


def test_citation_guard_should_defer_when_no_hint() -> None:
    state = {
        "citation_policy": "required_focus",
        "focus_reference": None,
        "candidates": [],
    }
    result = citation_guard_node(state)
    assert result.get("planned_action") == "listen_only"
