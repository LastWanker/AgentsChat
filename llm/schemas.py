from __future__ import annotations

import json
from typing import Any, Dict

from events.intention_schemas import IntentionDraft


TAG_GENERATION_SCHEMA: Dict[str, Any] = {
    "title": "标签生成",
    "type": "object",
    "required": ["tags"],
    "properties": {
        "tags": {
            "type": "array",
            "description": "学科性/方面性/总结性关键词，需短词且不超过 max_tags",
            "items": {"type": "string"},
        }
    },
}

INTENTION_DRAFT_SCHEMA: Dict[str, Any] = {
    "title": "意向草稿",
    "type": "object",
    "required": [
        "kind",
        "draft_text",
        "retrieval_tags",
        "confidence",
        "motivation",
        "urgency",
    ],
    "properties": {
        "kind": {"type": "string", "description": "意向类型，如 speak/submit"},
        "draft_text": {"type": "string", "description": "面向群内其他成员的草稿文本（我打算说/提交的内容）"},
        "retrieval_tags": {
            "type": "array",
            "description": "用于索引的 tags（优先从 tags 池选取，建议 6~12 个）",
            "items": {"type": "string"},
        },
        "retrieval_keywords": {
            "type": "array",
            "description": "不在 tags 池中的额外关键词，将进行全文检索",
            "items": {"type": "string"},
        },
        "confidence": {"type": "number", "description": "对主题了解程度(0~1)"},
        "motivation": {"type": "number", "description": "兴趣/回答意愿(0~1)"},
        "urgency": {"type": "number", "description": "重要性/紧迫性(0~1)"},
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
        "tags": {
            "type": "array",
            "description": "事件 tags（不超过 6 个，前两个固定为 agent 标签）",
            "items": {"type": "string"},
        },
        "references": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["event_id", "weight"],
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


def parse_intention_final(payload: str) -> Dict[str, Any]:
    """从 LLM 输出里解析 FinalIntention 字典。"""

    return _extract_json(payload)


def parse_tag_generation(payload: str) -> Dict[str, Any]:
    """从 LLM 输出里解析 tags 生成结果。"""

    return _extract_json(payload)


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
