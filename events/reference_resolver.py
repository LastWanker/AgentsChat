from __future__ import annotations

"""LLM-free reference resolver using naive query strategies."""

from typing import List, Optional

from events.intention_schemas import IntentionDraft
from events.query import EventQuery
from events.references import default_ref_weight, normalize_references
from events.types import Event, Reference
from events.session_memory import TagPool


class ReferenceResolver:
    """Resolve candidate references from a draft's retrieval plan."""

    def __init__(self, query: EventQuery, *, tag_pool: Optional[TagPool] = None):
        self.query = query
        self.tag_pool = tag_pool

    def resolve(self, draft: IntentionDraft) -> List[Reference]:
        candidates: List[Reference] = []
        seen: set[str] = set()

        draft_id = getattr(draft, "intention_id", None) or "<no-id>"
        recent_limit = self._recent_limit(draft)
        print(
            f"[events/reference_resolver.py] 🔍 草稿 {draft_id} 基于 tags+最近事件+关键词生成引用，recent={recent_limit}."
        )

        event_ids: List[str] = []
        if self.tag_pool and draft.retrieval_tags:
            event_ids.extend(self.tag_pool.event_ids_for_tags(draft.retrieval_tags))
        if draft.retrieval_keywords:
            for ev in self.query.search(keywords=draft.retrieval_keywords, limit=None):
                event_ids.append(ev.event_id)
        event_ids.extend([ev.event_id for ev in self.query.recent(n=recent_limit)])

        for event_id in event_ids:
            if event_id in seen:
                continue
            event = self.query.by_id(event_id)
            if not event:
                continue
            seen.add(event_id)
            candidates.append({"event_id": event.event_id, "weight": default_ref_weight()})

        print(
            f"[events/reference_resolver.py] 🧮 检索完成，草稿 {draft_id} 收集到 {len(candidates)} 条引用。"
        )

        return normalize_references(candidates)

    # --- internals ---
    @staticmethod
    def _recent_limit(draft: IntentionDraft) -> int:
        agent_count = draft.agent_count or 0
        return max(6, agent_count * 2) if agent_count else 6
