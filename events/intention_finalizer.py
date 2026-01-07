"""Glue DraftIntention -> FinalIntention with resolver guardrails."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from events.intention_schemas import FinalIntention, IntentionDraft
from events.types import Intention, Reference
from events.reference_resolver import ReferenceResolver
from events.references import default_ref_weight
from llm.client import LLMRequestOptions
from llm.prompts import build_intention_prompt
from llm.schemas import parse_intention_final


@dataclass
class FinalizerConfig:
    enable_llm: bool = False
    llm_mode: str = "sync"


class IntentionFinalizer:
    def __init__(
        self,
        resolver: ReferenceResolver,
        *,
        config: Optional[FinalizerConfig] = None,
        llm_client: Optional[Any] = None,
    ):
        self.resolver = resolver
        self.config = config or FinalizerConfig()
        self.llm_client = llm_client

    def finalize(self, draft: IntentionDraft, *, agent_id: str, intention_id: str) -> Intention:
        """Convert a draft into a routed Intention using resolver-only references."""

        if not draft.retrieval_plan:
            raise ValueError("DraftIntention 缺少 retrieval_plan，无法生成可追溯引用。")

        print(
            f"[events/intention_finalizer.py] 🧭 进入两段式生成的第二段：为草稿 {intention_id} 解析引用。",
            f"检索计划 {len(draft.retrieval_plan)} 条。",
        )
        candidate_refs = self.resolver.resolve(draft)

        print(
            f"[events/intention_finalizer.py] 🏁 草稿 {intention_id} 的引用解析完成，拿到 {len(candidate_refs)} 条候选引用。",
        )

        final = self._finalize_with_llm(draft, candidate_refs) if self._use_llm() else None
        if final is None:
            weighted_refs = self._apply_weight_defaults(candidate_refs, draft)
            final = FinalIntention(
                kind=draft.kind,
                payload=self._payload_for_kind(draft),
                references=weighted_refs,
                candidate_references=weighted_refs,
                target_scope=draft.target_scope,
                completed=True,
                confidence=draft.confidence,
                motivation=draft.motivation,
                urgency=draft.urgency,
            )

        return final.to_intention(
            agent_id=agent_id,
            intention_id=intention_id,
            scope=draft.target_scope,
            confidence=draft.confidence,
            motivation=draft.motivation,
            urgency=draft.urgency,
        )

    @staticmethod
    def _payload_for_kind(draft: IntentionDraft) -> dict:
        kind = (draft.kind or "").lower()
        message = draft.draft_text or draft.message_plan
        if kind in ("speak", "speak_public"):
            return {"text": message}
        if kind == "submit":
            return {"result": message}
        if kind == "evaluation":
            return {"score": message}
        if kind in ("request_anyone", "request_specific", "request_all"):
            return {"request": message}
        return {"text": message}

    def _use_llm(self) -> bool:
        return bool(self.config.enable_llm and self.llm_client is not None)

    def _finalize_with_llm(
            self, draft: IntentionDraft, candidate_refs: List[Reference]
    ) -> Optional[FinalIntention]:
        if not self._use_llm():
            return None

        candidate_events = []
        for ref in candidate_refs:
            ev = self.resolver.query.by_id(ref.get("event_id"))
            if ev:
                candidate_events.append(ev.__dict__ if hasattr(ev, "__dict__") else dict(ev))

        trigger_event = {
            "sender": draft.agent_id,
            "type": draft.kind,
            "scope": draft.target_scope,
            "content": self._payload_for_kind(draft),
        }
        messages = build_intention_prompt(
            agent_name=str(draft.agent_id or "agent"),
            agent_role=None,
            trigger_event=trigger_event,
            recent_events=[],
            referenced_events=[],
            draft_intention=draft.to_dict(),
            candidate_references=candidate_refs,
            candidate_events=candidate_events,
            phase="finalize",
        )
        options = LLMRequestOptions(stream=self.config.llm_mode == "stream")

        if self.config.llm_mode == "async":
            import asyncio

            content = asyncio.run(self.llm_client.acomplete(messages, options=options))
        elif self.config.llm_mode == "stream":
            content = "".join(self.llm_client.stream(messages, options=options))
        else:
            content = self.llm_client.complete(messages, options=options)

        try:
            data = parse_intention_final(content)
        except Exception as exc:  # noqa: BLE001
            print(
                "[events/intention_finalizer.py] ⚠️ finalize 输出解析失败，回退规则权重：",
                f"{type(exc).__name__}: {exc}",
            )
            return None

        final = FinalIntention.from_dict(data)
        allowed_ids = {ref.get("event_id") for ref in candidate_refs}
        filtered_refs = [
            ref for ref in final.references if ref.get("event_id") in allowed_ids
        ]
        if not filtered_refs:
            return None
        final.references = self._ensure_weight_fields(filtered_refs, draft)
        final.candidate_references = final.references
        final.confidence = draft.confidence
        final.motivation = draft.motivation
        final.urgency = draft.urgency
        return final

    def _apply_weight_defaults(
            self, refs: List[Reference], draft: IntentionDraft
    ) -> List[Reference]:
        default_weight = self._weight_from_draft(draft)
        return self._ensure_weight_fields(refs, draft, default_weight=default_weight)

    def _ensure_weight_fields(
            self,
            refs: List[Reference],
            draft: IntentionDraft,
            *,
            default_weight: Optional[Dict[str, float]] = None,
    ) -> List[Reference]:
        weighted: List[Reference] = []
        fallback = default_weight or self._weight_from_draft(draft)
        for ref in refs:
            weight = dict(default_ref_weight())
            weight.update(ref.get("weight", {}) or {})
            for key, value in fallback.items():
                if weight.get(key) in (None, 0.0):
                    weight[key] = value
            weighted.append({"event_id": ref.get("event_id"), "weight": weight})
        return weighted

    @staticmethod
    def _weight_from_draft(draft: IntentionDraft) -> Dict[str, float]:
        stance = max(-1.0, min(1.0, (draft.motivation * 2.0) - 1.0))
        return {
            "stance": stance,
            "inspiration": draft.confidence,
            "dependency": draft.urgency,
        }