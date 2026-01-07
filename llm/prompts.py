from __future__ import annotations

import json
from typing import Dict, List

from llm.schemas import schema_for_phase


SYSTEM_ROLE_LIBRARY: Dict[str, str] = {
    "boss": "你是 BOSS，负责控场、收口、做最终判断。",
    "thinker": "你是思考者，负责拆解问题、提出方案。",
    "critic": "你是质疑者，负责指出风险与漏洞。",
    "default": "你是团队成员，请保持专业、简洁、可执行。",
}


def build_intention_prompt(
    *,
    agent_name: str,
    agent_role: str | None,
    trigger_event: Dict[str, str],
    phase: str = "draft",
) -> List[Dict[str, str]]:
    """构造两段式生成的提示词，默认 draft 阶段。"""

    role_key = (agent_role or "default").lower()
    role_desc = SYSTEM_ROLE_LIBRARY.get(role_key, SYSTEM_ROLE_LIBRARY["default"])
    schema = schema_for_phase(phase)
    system = (
        "你在一个工作群聊中参与讨论。"
        "输出必须是 JSON，且严格遵守给定 schema。"
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

    user = (
        "当前触发事件如下：\n"
        f"sender={trigger_event.get('sender')}\n"
        f"type={trigger_event.get('type')}\n"
        f"scope={trigger_event.get('scope')}\n"
        f"content={trigger_event.get('content', trigger_event.get('payload'))}\n"
        "请给出本阶段 JSON 输出。"
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]