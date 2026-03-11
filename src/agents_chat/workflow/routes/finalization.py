from __future__ import annotations

from events.intention_schemas import IntentionDraft


def should_finalize(draft: IntentionDraft) -> bool:
    score = draft.confidence + draft.motivation + draft.urgency
    return score > 1.0 or max(draft.confidence, draft.motivation, draft.urgency) > 0.5

