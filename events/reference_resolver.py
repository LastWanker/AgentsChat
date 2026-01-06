from __future__ import annotations

"""LLM-free reference resolver using naive query strategies."""

from typing import List, Optional

from events.intention_schemas import IntentionDraft, RetrievalInstruction
from events.query import EventQuery
from events.references import default_ref_weight, normalize_references
from events.types import Event, Reference


class ReferenceResolver:
    """Resolve candidate references from a draft's retrieval plan."""

    def __init__(self, query: EventQuery):
        self.query = query

    def resolve(self, draft: IntentionDraft) -> List[Reference]:
        candidates: List[Reference] = []
        seen: set[str] = set()

        for instruction in draft.retrieval_plan:
            scope = instruction.scope or draft.target_scope
            events = self._execute_instruction(instruction, scope)
            for ev in events:
                if ev.event_id in seen:
                    continue
                seen.add(ev.event_id)
                candidates.append({"event_id": ev.event_id, "weight": default_ref_weight()})

        return normalize_references(candidates)

    # --- internals ---
    def _execute_instruction(
        self, instruction: RetrievalInstruction, scope: Optional[str]
    ) -> List[Event]:
        if instruction.after_event_id:
            base_event = self.query.by_id(instruction.after_event_id)
            chain: List[Event] = []
            if base_event and (scope is None or base_event.scope == scope):
                chain.append(base_event)

            if instruction.thread_depth > 0:
                chain.extend(self.query.thread_up(instruction.after_event_id, instruction.thread_depth))

            return chain

        if instruction.keywords:
            if not scope:
                return []
            return self.query.search(
                scope=scope,
                keywords=instruction.keywords,
                limit=instruction.limit,
                event_types=instruction.event_types or None,
                after_time=instruction.after_time,
            )

        if scope:
            return self.query.recent(scope=scope, n=instruction.limit)

        return []