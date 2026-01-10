from __future__ import annotations

"""
Two-phase intention schema definitions.

These dataclasses are intentionally serialization-friendly so they can be
persisted, inspected, and unit-tested without LLM dependencies.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from events.references import normalize_references
from events.types import Intention, Reference


@dataclass
class IntentionDraft:
    """LLM-ready draft without references.

    Represents the first phase: decide what to do and which evidence to look up,
    but never fill references yet.
    """

    kind: str
    draft_text: str = ""
    retrieval_tags: List[str] = field(default_factory=list)
    retrieval_keywords: List[str] = field(default_factory=list)
    target_scope: Optional[str] = None
    visibility: Optional[str] = None
    confidence: float = 0.0
    motivation: float = 0.0
    urgency: float = 0.0
    message_plan: str = ""

    # runtime fields (kept lightweight to allow queueing without Intention)
    intention_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent_role: Optional[str] = None
    agent_count: Optional[int] = None
    agent_name: Optional[str] = None
    agent_expertise: List[str] = field(default_factory=list)
    status: str = "pending"
    deferred_until_tick: Optional[int] = None
    deferred_until_time: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.draft_text:
            self.draft_text = self.message_plan
        self.draft_text = _coerce_text(self.draft_text)
        self.confidence = self._clamp_unit(self.confidence)
        self.motivation = self._clamp_unit(self.motivation)
        self.urgency = self._clamp_unit(self.urgency)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "IntentionDraft":
        return cls(
            kind=raw["kind"],
            draft_text=_coerce_text(
                raw.get("draft_text", raw.get("text", raw.get("message_plan", "")))
            ),
            retrieval_tags=list(raw.get("retrieval_tags", []) or []),
            retrieval_keywords=list(raw.get("retrieval_keywords", []) or []),
            target_scope=raw.get("target_scope"),
            visibility=raw.get("visibility"),
            confidence=float(raw.get("confidence", 0.0)),
            motivation=float(raw.get("motivation", 0.0)),
            urgency=float(raw.get("urgency", 0.0)),
            message_plan=raw.get("message_plan", ""),
            agent_role=raw.get("agent_role"),
            agent_count=raw.get("agent_count"),
            agent_name=raw.get("agent_name"),
            agent_expertise=list(raw.get("agent_expertise", []) or []),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "draft_text": self.draft_text,
            "retrieval_tags": list(self.retrieval_tags),
            "retrieval_keywords": list(self.retrieval_keywords),
            "target_scope": self.target_scope,
            "visibility": self.visibility,
            "confidence": self.confidence,
            "motivation": self.motivation,
            "urgency": self.urgency,
            "message_plan": self.message_plan,
            "agent_role": self.agent_role,
            "agent_count": self.agent_count,
            "agent_name": self.agent_name,
            "agent_expertise": list(self.agent_expertise),
        }

    @staticmethod
    def _clamp_unit(value: float) -> float:
        try:
            value = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, value))


def _coerce_text(value: Any) -> str:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                return _coerce_text(json.loads(text))
            except json.JSONDecodeError:
                return text
        return text
    if isinstance(value, dict):
        for key in ("text", "content", "message", "result", "request", "score"):
            if key in value and value[key] is not None:
                return _coerce_text(value[key])
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    return str(value)


@dataclass
class FinalIntention:
    """Finalized intention with normalized references."""

    kind: str
    payload: Dict[str, Any]
    references: List[Reference]
    target_scope: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    completed: bool = True
    confidence: float = 0.0
    motivation: float = 0.0
    urgency: float = 0.0

    def __post_init__(self) -> None:
        if not self.references:
            print(
                "[FinalIntention] warning: created without references;"
                " downstream consumers should ensure evidence is attached"
            )
        self.references = normalize_references(self.references)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "FinalIntention":
        return cls(
            kind=raw["kind"],
            payload=raw.get("payload", {}),
            references=raw.get("references") or [],
            target_scope=raw.get("target_scope"),
            tags=list(raw.get("tags", []) or []),
            completed=bool(raw.get("completed", True)),
            confidence=float(raw.get("confidence", 0.0)),
            motivation=float(raw.get("motivation", 0.0)),
            urgency=float(raw.get("urgency", 0.0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "payload": self.payload,
            "references": [dict(r) for r in self.references],
            "target_scope": self.target_scope,
            "tags": list(self.tags),
            "completed": self.completed,
            "confidence": self.confidence,
            "motivation": self.motivation,
            "urgency": self.urgency,
        }

    def to_intention(
            self,
            *,
            agent_id: str,
            intention_id: str,
            scope: Optional[str] = None,
            confidence: float | None = None,
            motivation: float | None = None,
            urgency: float | None = None,
    ) -> Intention:
        return Intention(
            intention_id=intention_id,
            agent_id=agent_id,
            kind=self.kind,
            payload=self.payload,
            scope=scope or self.target_scope or "public",
            references=self.references,
            tags=list(self.tags),
            completed=self.completed,
            confidence=self.confidence if confidence is None else confidence,
            motivation=self.motivation if motivation is None else motivation,
            urgency=self.urgency if urgency is None else urgency,
        )
