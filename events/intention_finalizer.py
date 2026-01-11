"""Glue DraftIntention -> FinalIntention with resolver guardrails."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from events.intention_schemas import FinalIntention, IntentionDraft
from events.types import Intention, Reference
from events.reference_resolver import ReferenceResolver
from events.references import default_ref_weight
from config.roles import role_temperature
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
        memory: Optional[Any] = None,
    ):
        self.resolver = resolver
        self.config = config or FinalizerConfig()
        self.llm_client = llm_client
        self.memory = memory

    def finalize(self, draft: IntentionDraft, *, agent_id: str, intention_id: str) -> Intention:
        """Convert a draft into a routed Intention using resolver-only references."""
        print(
            f"[events/intention_finalizer.py] 🧭 进入两段式生成的第二段：为草稿 {intention_id} 解析引用。",
            f"索引 tags={len(draft.retrieval_tags)}。",
        )
        candidate_refs = self.resolver.resolve(draft)

        print(
            f"[events/intention_finalizer.py] 🏁 草稿 {intention_id} 的引用解析完成，拿到 {len(candidate_refs)} 条候选引用。",
        )

        final = self._finalize_with_llm(draft, candidate_refs) if self._use_llm() else None
        if final is None:
            weighted_refs = self._apply_weight_defaults(candidate_refs)
            final = FinalIntention(
                kind=draft.kind,
                payload=self._payload_for_kind(draft),
                references=weighted_refs,
                tags=self._normalize_draft_tags(draft.retrieval_tags),
                confidence=draft.confidence,
                motivation=draft.motivation,
                urgency=draft.urgency,
            )
        else:
            final.tags = self._normalize_draft_tags(draft.retrieval_tags)

        return final.to_intention(
            agent_id=agent_id,
            intention_id=intention_id,
            confidence=draft.confidence,
            motivation=draft.motivation,
            urgency=draft.urgency,
        )

    @staticmethod
    def _payload_for_kind(draft: IntentionDraft) -> dict:
        kind = (draft.kind or "").lower()
        message = IntentionFinalizer._normalize_message(draft.draft_text or draft.message_plan)
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
            "content": self._payload_for_kind(draft),
        }
        messages = build_intention_prompt(
            agent_name=str(draft.agent_id or "agent"),
            agent_role=draft.agent_role,
            trigger_event=trigger_event,
            recent_events=[],
            referenced_events=[],
            personal_tasks=self._personal_tasks_payload(draft.agent_id),
            tag_pool=self._tag_pool_payload(),
            team_board=self._team_board_payload(),
            draft_intention=draft.to_dict(),
            candidate_events=candidate_events,
            phase="finalize",
        )
        options = LLMRequestOptions(
            stream=self.config.llm_mode == "stream",
            temperature=role_temperature(draft.agent_role),
        )

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
        final.payload = self._normalize_payload(final.kind, final.payload)
        final.references = self._apply_weight_defaults(candidate_refs)
        final.tags = self._normalize_draft_tags(draft.retrieval_tags)
        final.confidence = draft.confidence
        final.motivation = draft.motivation
        final.urgency = draft.urgency
        return final

    def _personal_tasks_payload(self, agent_id: Optional[str]) -> Dict[str, Any]:
        if not self.memory or not agent_id:
            return {}
        table = self.memory.personal_table_for(agent_id)
        return {"done_list": table.done_list, "todo_list": table.todo_list}

    def _tag_pool_payload(self) -> Dict[str, Any]:
        if not self.memory:
            return {}
        return self.memory.tag_pool_payload()

    def _team_board_payload(self) -> List[Dict[str, Any]]:
        if not self.memory:
            return []
        return self.memory.team_board_payload()

    def _apply_weight_defaults(self, refs: List[Reference]) -> List[Reference]:
        default_weight = default_ref_weight()
        return self._ensure_weight_fields(refs, default_weight=default_weight)

    def _ensure_weight_fields(
        self,
        refs: List[Reference],
        *,
        default_weight: Optional[Dict[str, float]] = None,
    ) -> List[Reference]:
        weighted: List[Reference] = []
        fallback = default_weight or default_ref_weight()
        for ref in refs:
            weight = dict(default_ref_weight())
            weight.update(ref.get("weight", {}) or {})
            for key, value in fallback.items():
                if weight.get(key) in (None, 0.0):
                    weight[key] = value
            weighted.append({"event_id": ref.get("event_id"), "weight": weight})
        return weighted

    @staticmethod
    def _normalize_draft_tags(tags: List[str], max_tags: int = 9) -> List[str]:
        seen = set()
        normalized: List[str] = []
        for tag in tags or []:
            if not tag:
                continue
            key = str(tag).lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(str(tag))
            if len(normalized) >= max_tags:
                break
        return normalized

    @staticmethod
    def _normalize_message(value: Any) -> str:
        global json
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("{") and text.endswith("}"):
                try:
                    import json

                    return IntentionFinalizer._normalize_message(json.loads(text))
                except json.JSONDecodeError:
                    return text
            return text
        if isinstance(value, dict):
            for key in ("text", "content", "message"):
                if key in value and value[key] is not None:
                    return IntentionFinalizer._normalize_message(value[key])
            import json

            return json.dumps(value, ensure_ascii=False)
        if value is None:
            return ""
        return str(value)

    @classmethod
    def _normalize_payload(cls, kind: str, payload: Any) -> Dict[str, Any]:
        expected_key = "text"
        if isinstance(payload, dict):
            if expected_key in payload and payload[expected_key] is not None:
                return {expected_key: cls._normalize_message(payload[expected_key])}
            for key in ("text", "content", "message"):
                if key in payload and payload[key] is not None:
                    return {expected_key: cls._normalize_message(payload[key])}
            return {expected_key: cls._normalize_message(payload)}
        return {expected_key: cls._normalize_message(payload)}
