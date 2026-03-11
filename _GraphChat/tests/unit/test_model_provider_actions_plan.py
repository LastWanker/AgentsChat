from __future__ import annotations

from graphchat.infrastructure.llm.model_provider import (
    LangChainStructuredModelProvider,
    RuleBasedModelProvider,
)


def test_rule_based_model_provider_should_output_v2_and_v1_compat() -> None:
    provider = RuleBasedModelProvider()
    plan = provider.plan_action(
        {
            "last_event": {
                "payload": {"text": "请更新任务板并同步"},
            }
        }
    )
    assert plan.get("plan_version") == "v2"
    assert isinstance(plan.get("actions"), list) and len(plan["actions"]) == 1
    assert plan["actions"][0]["action_id"] == "maintain_board"
    assert plan.get("action") == "maintain_board"  # V1 compatibility
    assert plan.get("payload", {}).get("world_scope") == "group:main"


def test_structured_provider_should_sort_by_step_index() -> None:
    class _Parsed:
        reasoning_summary = "ok"
        task_done = False
        actions = [
            {
                "action_id": "speak",
                "plan_text": "[speak] 汇报",
                "payload": {"text": "汇报", "world_scope": "group:main"},
                "target_scope": "group:main",
                "target_agents": [],
                "priority": 20,
                "can_skip": False,
                "step_index": 2,
            },
            {
                "action_id": "maintain_board",
                "plan_text": "[board] 更新",
                "payload": {"board_op": "upsert", "text": "任务", "world_scope": "group:main"},
                "target_scope": "group:main",
                "target_agents": [],
                "priority": 10,
                "can_skip": False,
                "step_index": 1,
            },
        ]

    class _Structured:
        def invoke(self, _messages):
            return _Parsed()

    class _FakeLLM:
        def with_structured_output(self, _schema):
            return _Structured()

    provider = LangChainStructuredModelProvider(
        llm=_FakeLLM(),
        allowed_actions={"speak", "maintain_board"},
        fallback=RuleBasedModelProvider(),
    )
    plan = provider.plan_action(
        {
            "last_event": {"payload": {"text": "hello"}},
            "visible_events": [],
        }
    )
    actions = plan.get("actions", [])
    assert [x["action_id"] for x in actions] == ["maintain_board", "speak"]
    assert plan.get("action") == "maintain_board"  # V1 compatibility
