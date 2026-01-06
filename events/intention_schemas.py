from __future__ import annotations

"""
Two-phase intention schema definitions.

These dataclasses are intentionally serialization-friendly so they can be
persisted, inspected, and unit-tested without LLM dependencies.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from events.references import normalize_references
from events.types import Intention, Reference


@dataclass
class RetrievalInstruction:
    """Describe one retrieval need for an intention draft."""

    name: str
    keywords: List[str] = field(default_factory=list)
    event_types: List[str] = field(default_factory=list)
    scope: Optional[str] = None
    after_event_id: Optional[str] = None
    after_time: Optional[str] = None
    thread_depth: int = 0
    limit: int = 5

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "RetrievalInstruction":
        return cls(
            name=raw.get("name", "plan"),
            keywords=list(raw.get("keywords", []) or []),
            event_types=list(raw.get("event_types", []) or []),
            scope=raw.get("scope"),
            after_event_id=raw.get("after_event_id"),
            after_time=raw.get("after_time"),
            thread_depth=int(raw.get("thread_depth", 0) or 0),
            limit=int(raw.get("limit", 5) or 5),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IntentionDraft:
    """LLM-ready draft without references.

    Represents the first phase: decide what to do and which evidence to look up,
    but never fill references yet.
    """

    kind: str
    message_plan: str
    retrieval_plan: List[RetrievalInstruction] = field(default_factory=list)
    target_scope: Optional[str] = None
    visibility: Optional[str] = None

    # runtime fields (kept lightweight to allow queueing without Intention)
    intention_id: Optional[str] = None
    agent_id: Optional[str] = None
    status: str = "pending"
    deferred_until_tick: Optional[int] = None
    deferred_until_time: Optional[float] = None
    urgency: float = 0.0

    def __post_init__(self) -> None:
        self.retrieval_plan = [self._ensure_instruction(p) for p in self.retrieval_plan]

    @staticmethod
    def _ensure_instruction(plan: RetrievalInstruction | Dict[str, Any]) -> RetrievalInstruction:
        if isinstance(plan, RetrievalInstruction):
            return plan
        if isinstance(plan, dict):
            return RetrievalInstruction.from_dict(plan)
        raise TypeError(f"Unsupported retrieval plan entry: {plan!r}")

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "IntentionDraft":
        return cls(
            kind=raw["kind"],
            message_plan=raw.get("message_plan", ""),
            retrieval_plan=raw.get("retrieval_plan", []),
            target_scope=raw.get("target_scope"),
            visibility=raw.get("visibility"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "message_plan": self.message_plan,
            "retrieval_plan": [p.to_dict() for p in self.retrieval_plan],
            "target_scope": self.target_scope,
            "visibility": self.visibility,
        }


@dataclass
class FinalIntention:
    """Finalized intention with normalized references."""

    kind: str
    payload: Dict[str, Any]
    references: List[Reference]
    target_scope: Optional[str] = None
    candidate_references: List[Reference] = field(default_factory=list)
    completed: bool = True

    def __post_init__(self) -> None:
        if not self.references:
            print(
                "[FinalIntention] warning: created without references;"
                " downstream consumers should ensure evidence is attached"
            )
        self.references = normalize_references(self.references)
        self.candidate_references = normalize_references(self.candidate_references or [])

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "FinalIntention":
        return cls(
            kind=raw["kind"],
            payload=raw.get("payload", {}),
            references=raw.get("references") or [],
            target_scope=raw.get("target_scope"),
            candidate_references=raw.get("candidate_references", []),
            completed=bool(raw.get("completed", True)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "payload": self.payload,
            "references": [dict(r) for r in self.references],
            "target_scope": self.target_scope,
            "candidate_references": [dict(r) for r in self.candidate_references],
            "completed": self.completed,
        }

    def to_intention(
            self,
            *,
            agent_id: str,
            intention_id: str,
            scope: Optional[str] = None,
    ) -> Intention:
        return Intention(
            intention_id=intention_id,
            agent_id=agent_id,
            kind=self.kind,
            payload=self.payload,
            scope=scope or self.target_scope or "public",
            candidate_references=self.candidate_references,
            references=self.references,
            completed=self.completed,
        )
