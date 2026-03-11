# import pytest

from events.intention_schemas import FinalIntention, IntentionDraft
from events.types import Intention


class TestIntentionDraft:
    def test_round_trip(self):
        draft = IntentionDraft(
            kind="speak",
            draft_text="回应最新的发言并引用历史决策",
            retrieval_tags=["讨论", "决策"],
        )

        payload = draft.to_dict()
        restored = IntentionDraft.from_dict(payload)

        assert restored.kind == "speak"
        assert restored.retrieval_tags == ["讨论", "决策"]


class TestFinalIntention:
    def test_warns_when_missing_references(self, capsys):
        final = FinalIntention(kind="speak", payload={"text": "hi"}, references=[])

        captured = capsys.readouterr()
        assert "warning: created without references" in captured.out
        assert final.references == []

    def test_normalization_and_conversion(self):
        final = FinalIntention(
            kind="speak",
            payload={"text": "ok"},
            references=["evt-2", {"event_id": "evt-3", "weight": {"dependency": 1}}],
            tags=["agent", "领域"],
        )

        as_dict = final.to_dict()
        restored = FinalIntention.from_dict(as_dict)
        assert restored.references[0]["weight"]["stance"] == 0.1

        intention: Intention = restored.to_intention(
            agent_id="agent-1", intention_id="int-1"
        )
        assert intention.references[1]["weight"]["dependency"] == 1
