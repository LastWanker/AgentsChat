# import pytest

from events.intention_schemas import (
    FinalIntention,
    IntentionDraft,
    RetrievalInstruction,
)
from events.types import Intention


class TestIntentionDraft:
    def test_round_trip(self):
        draft = IntentionDraft(
            kind="speak",
            message_plan="回应最新的发言并引用历史决策",
            retrieval_plan=[
                RetrievalInstruction(
                    name="latest",
                    keywords=["讨论", "决策"],
                    event_types=["speak"],
                    scope="public",
                    limit=3,
                ),
                {"name": "thread", "thread_depth": 2, "after_event_id": "evt-1"},
            ],
            target_scope="public",
        )

        payload = draft.to_dict()
        restored = IntentionDraft.from_dict(payload)

        assert restored.kind == "speak"
        assert len(restored.retrieval_plan) == 2
        assert restored.retrieval_plan[0].keywords == ["讨论", "决策"]
        assert restored.retrieval_plan[1].thread_depth == 2


class TestFinalIntention:
    def test_warns_when_missing_references(self, capsys):
        final = FinalIntention(kind="speak", payload={"text": "hi"}, references=[])

        captured = capsys.readouterr()
        assert "warning: created without references" in captured.out
        assert final.references == []

    def test_normalization_and_conversion(self):
        final = FinalIntention(
            kind="submit",
            payload={"result": "ok"},
            references=["evt-2", {"event_id": "evt-3", "weight": {"dependency": 1}}],
            candidate_references=[{"event_id": "evt-4"}],
            target_scope="group:1",
        )

        as_dict = final.to_dict()
        restored = FinalIntention.from_dict(as_dict)
        assert restored.references[0]["weight"]["stance"] == 0.0

        intention: Intention = restored.to_intention(
            agent_id="agent-1", intention_id="int-1", scope="group:1"
        )
        assert intention.scope == "group:1"
        assert intention.references[1]["weight"]["dependency"] == 1