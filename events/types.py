from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, TypedDict
from uuid import uuid4
from datetime import datetime, UTC

Scope = str  # "public" or "group:<id>"


class RefWeight(TypedDict, total=False):
    stance: float  # [-1, 1] 认可/反对（投票、评价）
    inspiration: float  # [0, 1] 启发度（被点醒程度）
    dependency: float  # [0, 1] 依赖度（数据/知识依赖）


class Reference(TypedDict, total=False):
    event_id: str  # 必填
    weight: RefWeight  # 可省略，省略视为 0 权重


@dataclass
class Intention:
    intention_id: str
    agent_id: str
    kind: str  # speak / submit / ...
    payload: Dict[str, Any]  # draft content
    scope: Scope = "public"
    candidate_references: List[Reference] = field(default_factory=list)
    references: List[Reference] = field(default_factory=list)
    completed: bool = True
    urgency: float = 0.0
    status: Literal["pending", "suppressed", "approved", "executed"] = "pending"
    deferred_until_tick: Optional[int] = None
    deferred_until_time: Optional[float] = None

    def __post_init__(self):
        from events.references import normalize_references

        self.candidate_references = normalize_references(self.candidate_references or [])
        self.references = normalize_references(self.references or [])

@dataclass
class Event:
    event_id: str
    type: str
    timestamp: str
    sender: str
    scope: Scope
    content: Dict[str, Any]
    references: List[Reference] = field(default_factory=list)
    recipients: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    completed: bool = True


@dataclass
class Decision:
    status: Literal["approved", "suppressed"]
    violations: List[Dict[str, str]] = field(default_factory=list)


def new_event(*, sender: str, type: str, scope: Scope, content: Dict[str, Any],
              references: Optional[List[Reference | str]] = None,
              recipients: Optional[List[str]] = None,
              metadata: Optional[Dict[str, Any]] = None,
              completed: bool = True) -> Event:
    from events.references import normalize_references

    return Event(
        event_id=str(uuid4()),
        type=type,
        timestamp=datetime.now(UTC).isoformat(),
        sender=sender,
        scope=scope,
        content=content,
        references=normalize_references(references or []),
        recipients=recipients or [],
        metadata=metadata or {},
        completed=completed,
    )
