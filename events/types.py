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
    sender: str
    sender_name: str = ""
    sender_role: str = ""
    content: Dict[str, Any] = field(default_factory=dict)
    references: List[Reference] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


@dataclass
class Decision:
    status: Literal["approved"]
    violations: List[Dict[str, str]] = field(default_factory=list)


def normalize_event_dict(raw: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(raw or {})
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    sender_name = (
        data.get("sender_name")
        or metadata.get("sender_name")
        or metadata.get("name")
        or ""
    )
    sender_role = (
        data.get("sender_role")
        or metadata.get("sender_role")
        or metadata.get("role")
        or ""
    )
    data["sender_name"] = str(sender_name)
    data["sender_role"] = str(sender_role)
    data["metadata"] = metadata
    data.setdefault("content", {})
    data.setdefault("references", [])
    data.setdefault("tags", [])
    data.setdefault("timestamp", "")
    data.pop("recipients", None)
    return data


def new_event(*, sender: str, type: str, content: Dict[str, Any],
              references: Optional[List[Reference | str]] = None,
              tags: Optional[List[str]] = None,
              sender_name: Optional[str] = None,
              sender_role: Optional[str] = None,
              metadata: Optional[Dict[str, Any]] = None) -> Event:
    from events.references import normalize_references

    meta = dict(metadata or {})
    resolved_sender_name = (
        sender_name
        or meta.pop("sender_name", None)
        or meta.pop("name", None)
        or ""
    )
    resolved_sender_role = (
        sender_role
        or meta.pop("sender_role", None)
        or meta.pop("role", None)
        or ""
    )

    return Event(
        event_id=next_event_id(),
        type=type,
        sender=sender,
        sender_name=str(resolved_sender_name),
        sender_role=str(resolved_sender_role),
        content=content,
        references=normalize_references(references or []),
        tags=list(tags or []),
        metadata=meta,
        timestamp=datetime.now(UTC).isoformat(),
    )
