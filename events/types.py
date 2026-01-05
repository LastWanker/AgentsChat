from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, TypedDict, Union
from uuid import uuid4
from datetime import datetime, UTC

Scope = str  # "public" or "group:<id>"


class WeightedReference(TypedDict):
    event_id: str
    weight: float


Reference = Union[str, WeightedReference]


@dataclass
class Intention:
    intention_id: str
    agent_id: str
    kind: str  # speak / submit / ...
    payload: Dict[str, Any]  # draft content
    scope: Scope = "public"
    references: List[Reference] = field(default_factory=list)
    completed: bool = True
    urgency: float = 0.0
    status: Literal["pending", "suppressed", "approved", "executed"] = "pending"
    deferred_until_tick: Optional[int] = None
    deferred_until_time: Optional[float] = None


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
              references: Optional[List[Reference]] = None,
              recipients: Optional[List[str]] = None,
              metadata: Optional[Dict[str, Any]] = None,
              completed: bool = True) -> Event:
    return Event(
        event_id=str(uuid4()),
        type=type,
        timestamp=datetime.now(UTC).isoformat(),
        sender=sender,
        scope=scope,
        content=content,
        references=references or [],
        recipients=recipients or [],
        metadata=metadata or {},
        completed=completed,
    )
