from __future__ import annotations

import json
from typing import Any, Dict

from events.intention_schemas import IntentionDraft


INTENTION_DRAFT_SCHEMA: Dict[str, Any] = {
    "title": "意向草稿",
    "type": "object",
    "required": ["kind", "message_plan", "draft_text", "retrieval_plan"],
    "properties": {
        "kind": {"type": "string", "description": "意向类型，如 speak/submit"},
        "message_plan": {"type": "string", "description": "行动/回复计划"},
        "draft_text": {"type": "string", "description": "面向群内其他成员的草稿文本（我打算说/提交的内容）"},
        "retrieval_plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "event_types": {"type": "array", "items": {"type": "string"}},
                    "scope": {"type": "string"},
                    "after_event_id": {"type": "string"},
                    "thread_depth": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
                "required": ["name"],
            },
        },
        "target_scope": {"type": "string"},
        "visibility": {"type": "string"},
    },
}

INTENTION_FINAL_SCHEMA: Dict[str, Any] = {
    "title": "最终意向",
    "type": "object",
    "required": ["kind", "payload", "references"],
    "properties": {
        "kind": {"type": "string"},
        "payload": {"type": "object"},
        "references": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["event_id"],
                "properties": {
                    "event_id": {"type": "string"},
                        "weight": {
                        "type": "object",
                        "description": "引用权重：stance(-1..1, 反对到支持)，inspiration(0..1, 启发程度)，dependency(0..1, 依赖程度)",
                        "properties": {
                            "stance": {"type": "number"},
                            "inspiration": {"type": "number"},
                            "dependency": {"type": "number"},
                        },
                    },
                },
            },
        },
        "candidate_references": {"type": "array"},
        "completed": {"type": "boolean"},
    },
}


def schema_for_phase(phase: str) -> Dict[str, Any]:
    if phase == "draft":
        return INTENTION_DRAFT_SCHEMA
    if phase == "finalize":
        return INTENTION_FINAL_SCHEMA
    raise ValueError(f"未知阶段: {phase}")


def parse_intention_draft(payload: str) -> IntentionDraft:
    """从 LLM 输出里解析 IntentionDraft。"""

    data = _extract_json(payload)
    return IntentionDraft.from_dict(data)


def _extract_json(payload: str) -> Dict[str, Any]:
    payload = payload.strip()
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        start = payload.find("{")
        end = payload.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        snippet = payload[start : end + 1]
        return json.loads(snippet)