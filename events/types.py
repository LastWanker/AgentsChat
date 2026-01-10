from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, TypedDict
from datetime import datetime, UTC

from events.id_generator import next_event_id


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
    kind: str  # speak / ...
    payload: Dict[str, Any]  # draft content
    references: List[Reference] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.0
    motivation: float = 0.0
    urgency: float = 0.0

    def __post_init__(self):
        from events.references import normalize_references

        self.references = normalize_references(self.references or [])

@dataclass
class Event:
    event_id: str
    type: str
    timestamp: str
    sender: str
    content: Dict[str, Any]
    references: List[Reference] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    recipients: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Decision:
    status: Literal["approved"]
    violations: List[Dict[str, str]] = field(default_factory=list)


def new_event(*, sender: str, type: str, content: Dict[str, Any],
              references: Optional[List[Reference | str]] = None,
              tags: Optional[List[str]] = None,
              recipients: Optional[List[str]] = None,
              metadata: Optional[Dict[str, Any]] = None) -> Event:
    from events.references import normalize_references

    return Event(
        event_id=next_event_id(),
        type=type,
        timestamp=datetime.now(UTC).isoformat(),
        sender=sender,
        content=content,
        references=normalize_references(references or []),
        tags=list(tags or []),
        recipients=recipients or [],
        metadata=metadata or {},
    )
