from __future__ import annotations


def _is_visible(scope: str, event_scope: str, agent_id: str) -> bool:
    if event_scope == "group:main":
        return True
    if event_scope.startswith("group:"):
        return scope == event_scope or scope == "group:main"
    if event_scope.startswith("dm:"):
        return agent_id in event_scope.split(":")
    return False


def filter_visible_events(events: list[dict], scope: str, agent_id: str) -> list[dict]:
    return [event for event in events if _is_visible(scope, event.get("world_scope", ""), agent_id)]

