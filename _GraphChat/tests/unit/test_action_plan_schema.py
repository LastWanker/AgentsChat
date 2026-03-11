from __future__ import annotations

from graphchat.domain.models.schemas import validate_action_plan_v2


def test_validate_action_plan_v2_should_accept_ordered_actions() -> None:
    parsed, err = validate_action_plan_v2(
        reasoning_summary="test",
        task_done=False,
        actions=[
            {
                "action_id": "speak",
                "plan_text": "[speak] @boss 汇报",
                "payload": {"text": "汇报", "world_scope": "group:main"},
                "target_scope": "group:main",
                "target_agents": ["boss"],
                "step_index": 2,
                "priority": 20,
                "can_skip": False,
            },
            {
                "action_id": "maintain_board",
                "plan_text": "[board] 更新任务",
                "payload": {"board_op": "upsert", "text": "任务A", "world_scope": "group:main"},
                "target_scope": "group:main",
                "target_agents": [],
                "step_index": 1,
                "priority": 10,
                "can_skip": False,
            },
        ],
        allowed_actions={"speak", "maintain_board"},
    )
    assert err is None
    assert parsed is not None
    assert [x["action_id"] for x in parsed["actions"]] == ["maintain_board", "speak"]


def test_validate_action_plan_v2_should_reject_invalid_scope() -> None:
    parsed, err = validate_action_plan_v2(
        reasoning_summary="bad",
        task_done=False,
        actions=[
            {
                "action_id": "speak",
                "target_scope": "invalid_scope",
            }
        ],
    )
    assert parsed is None
    assert isinstance(err, str) and "invalid target_scope" in err
