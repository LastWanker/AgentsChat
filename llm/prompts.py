from __future__ import annotations

import json
from typing import Any, Dict, List

from llm.schemas import schema_for_phase


SYSTEM_ROLE_LIBRARY: Dict[str, str] = {
    "boss": "你是 BOSS，负责控场、收口、做最终判断；你经常进行evaluation行为。",
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
        "当触发事件为 request_* 且 completed=False 时，优先产出 kind=submit。"
        "draft 阶段的 draft_text 表示你打算对群里说/提交的草稿内容。"
        "finalize 阶段必须生成面向其他成员的最终成文内容，不要输出“我打算做什么”。"
        "draft 阶段必须提供意愿三维：confidence(了解程度)、motivation(兴趣/意愿)、urgency(自我信息重要性)，范围 0~1。"
        "finalize 阶段必须为每条引用生成 weight：stance(-1..1, 反对到支持)、inspiration(0..1, 启发程度)、dependency(0..1, 依赖程度)。"
        "引用必须覆盖所有对本次发言产生影响的事件（至少列出主要来源），每条引用的 weight 独立评估。"
        "references 中只允许 event_id 与 weight 两个字段，不要附带原事件内容。"
        "submit 类型必须显式给出 stance/inspiration/dependency，不可省略。"
        "event type 的选择必须与 message_plan 与 draft_text 保持一致："
        "你打算说话就用 speak/speak_public，想提交结果就用 submit，想发起请求就用 request_*，想评价就用 evaluation。"
        "阶段为：{phase}。"
        "\n你的名字是：{agent_name}"
        "\n始终以 {agent_name} 的身份思考与输出，不要混淆或扮演其他成员。"
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
        f"completed={trigger_event.get('completed')}",
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