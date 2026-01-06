"""Glue DraftIntention -> FinalIntention with resolver guardrails."""

from __future__ import annotations

from events.intention_schemas import FinalIntention, IntentionDraft
from events.types import Intention
from events.reference_resolver import ReferenceResolver


class IntentionFinalizer:
    def __init__(self, resolver: ReferenceResolver):
        self.resolver = resolver

    def finalize(self, draft: IntentionDraft, *, agent_id: str, intention_id: str) -> Intention:
        """Convert a draft into a routed Intention using resolver-only references."""

        if not draft.retrieval_plan:
            raise ValueError("DraftIntention 缺少 retrieval_plan，无法生成可追溯引用。")

        candidate_refs = self.resolver.resolve(draft)

        # Final 阶段：references 必须来自 resolver 返回的候选 event_id
        final = FinalIntention(
            kind=draft.kind,
            payload={"text": draft.message_plan},
            references=candidate_refs,
            candidate_references=candidate_refs,
            target_scope=draft.target_scope,
            completed=True,
        )

        return final.to_intention(
            agent_id=agent_id,
            intention_id=intention_id,
            scope=draft.target_scope,
        )