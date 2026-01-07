from __future__ import annotations

import json
from typing import Any, Dict, List

from llm.schemas import schema_for_phase


SYSTEM_ROLE_LIBRARY: Dict[str, str] = {
    "boss": "你是 BOSS，负责控场、收口、做最终判断。",
    "thinker": "你是产出者，负责讲出观点。",
    "critic": "你是质疑者，负责挑刺儿。",
    "default": "你是团队成员，请保持专业、简洁、可执行。",
}


def build_intention_prompt(
    *,
    agent_name: str,
    agent_role: str | None,
    trigger_event: Dict[str, str],
    recent_events: List[Dict[str, str]] | None = None,
    referenced_events: List[Dict[str, str]] | None = None,
    draft_intention: Dict[str, Any] | None = None,
    candidate_references: List[Dict[str, Any]] | None = None,
    candidate_events: List[Dict[str, Any]] | None = None,
    phase: str = "draft",
) -> List[Dict[str, str]]:
    """构造两段式生成的提示词，默认 draft 阶段。"""

    role_key = (agent_role or "default").lower()
    role_desc = SYSTEM_ROLE_LIBRARY.get(role_key, SYSTEM_ROLE_LIBRARY["default"])
    schema = schema_for_phase(phase)
    system = (
        "你在一个工作群聊中参与讨论。"
        "输出必须是 JSON，且严格遵守给定 schema。"
        "当触发事件类型为 request_anyone/request_specific/request_all 时，优先产出 kind=submit。"
        "draft 阶段的 draft_text 表示你打算对群里说/提交的草稿内容。"
        "finalize 阶段必须生成面向其他成员的最终成文内容，不要输出“我打算做什么”。"
        "阶段为：{phase}。"
        "\n你的名字是：{agent_name}"
        "\n角色设定：{role_desc}"
        "\nschema:\n{schema_json}"
    ).format(
        phase=phase,
        role_desc=role_desc,
        agent_name=agent_name,
        schema_json=json.dumps(schema, ensure_ascii=False),
    )

    user_lines = [
        "当前触发事件如下：",
        f"sender={trigger_event.get('sender')}",
        f"type={trigger_event.get('type')}",
        f"scope={trigger_event.get('scope')}",
        f"content={trigger_event.get('content', trigger_event.get('payload'))}",
        "最近事件（可参考）：",
        json.dumps(recent_events or [], ensure_ascii=False),
        "触发事件引用链（可参考）：",
        json.dumps(referenced_events or [], ensure_ascii=False),
    ]
    if phase == "finalize":
        user_lines.extend(
            [
                "起草阶段输出（可参考）：",
                json.dumps(draft_intention or {}, ensure_ascii=False),
                "候选引用条目（可参考，包含 weight 字段）：",
                json.dumps(candidate_references or [], ensure_ascii=False),
                "候选事件完整内容（可参考）：",
                json.dumps(candidate_events or [], ensure_ascii=False),
            ]
        )
    user_lines.append("请给出本阶段 JSON 输出。")
    user = "\n".join(user_lines)

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]