from __future__ import annotations

from graphchat.domain.policies.scope_policy import filter_visible_events


def test_scope_visibility_world_group_dm() -> None:
    events = [
        {"event_id": "w1", "world_scope": "group:main"},
        {"event_id": "g1", "world_scope": "group:alpha"},
        {"event_id": "d1", "world_scope": "dm:agent_1:agent_2"},
        {"event_id": "d2", "world_scope": "dm:agent_3:agent_4"},
    ]

    vis_main = filter_visible_events(events, scope="group:main", agent_id="agent_1")
    vis_alpha = filter_visible_events(events, scope="group:alpha", agent_id="agent_1")

    ids_main = {e["event_id"] for e in vis_main}
    ids_alpha = {e["event_id"] for e in vis_alpha}

    assert "w1" in ids_main
    assert "g1" in ids_main  # 主群视角可看 group 事件（当前策略）
    assert "d1" in ids_main
    assert "d2" not in ids_main

    assert "w1" in ids_alpha
    assert "g1" in ids_alpha
    assert "d1" in ids_alpha

