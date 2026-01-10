from __future__ import annotations

import json
from typing import Any, Dict, List

from config.roles import role_prompt_description
from llm.schemas import TAG_GENERATION_SCHEMA, schema_for_phase


def build_intention_prompt(
    *,
    agent_name: str,
    agent_role: str | None,
    trigger_event: Dict[str, str],
    recent_events: List[Dict[str, str]] | None = None,
    referenced_events: List[Dict[str, str]] | None = None,
    personal_tasks: Dict[str, Any] | None = None,
    tag_pool: Dict[str, Any] | None = None,
    team_board: List[Dict[str, Any]] | None = None,
    draft_intention: Dict[str, Any] | None = None,
    candidate_events: List[Dict[str, Any]] | None = None,
    phase: str = "draft",
) -> List[Dict[str, str]]:
    """构造两段式生成的提示词，默认 draft 阶段。"""

    role_desc = role_prompt_description(agent_role)
    schema = schema_for_phase(phase)
    system = (
        "你在一个工作群聊中参与讨论。"
        "输出必须是 JSON，且严格遵守给定 schema。"
        "当触发事件为 request_* 且 completed=False 时，优先产出 kind=submit。"
        "draft 阶段的 draft_text 表示你打算对群里说/提交的草稿内容。"
        "finalize 阶段必须生成面向其他成员的最终成文内容，不要输出“我打算做什么”。"
        "draft 阶段必须提供意愿三维：confidence(了解程度)、motivation(兴趣/意愿)、urgency(自我信息重要性)，范围 0~1。"
        "draft 阶段需要输出 6~12 个 retrieval_tags，可适度补充 retrieval_keywords。"
        "finalize 阶段 references 将由系统自动填充，weight 采用默认值。"
        "event type 的选择必须与 draft_text 保持一致："
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
        "个人事务表（可参考）：",
        json.dumps(personal_tasks or {}, ensure_ascii=False),
        "tags 池（可参考）：",
        json.dumps(tag_pool or {}, ensure_ascii=False),
        "TeamBoard（可参考）：",
        json.dumps(team_board or [], ensure_ascii=False),
    ]
    if phase == "finalize":
        user_lines.extend(
            [
                "起草阶段输出（可参考）：",
                json.dumps(draft_intention or {}, ensure_ascii=False),
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


def build_tag_generation_prompt(
    *,
    text: str,
    max_tags: int = 6,
    fixed_prefix: List[str] | None = None,
    tag_pool: Dict[str, Any] | None = None,
) -> List[Dict[str, str]]:
    system = (
        "你是标签生成器。输出必须是 JSON，且严格遵守给定 schema。"
        "标签应是学科性/方面性/总结性关键词，避免寒暄词、口头语、碎片词。"
        "优先使用短词(2~6字)和高概括词，不要输出标点、语气词或停用词。"
        "不要输出与内容无关或重复的词。"
        f"最多 {max_tags} 个标签。"
        f"schema: {json.dumps(TAG_GENERATION_SCHEMA, ensure_ascii=False)}"
    )
    prefix = [t for t in (fixed_prefix or []) if t]
    user_lines = [
        "待分析内容：",
        text,
        "固定前缀(必须保留)：",
        json.dumps(prefix, ensure_ascii=False),
        "现有 tags 池(可参考)：",
        json.dumps(tag_pool or {}, ensure_ascii=False),
        "请输出 JSON。",
    ]
    user = "\n".join(user_lines)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_tag_generation_prompt(
    *,
    text: str,
    max_tags: int = 6,
    fixed_prefix: List[str] | None = None,
    tag_pool: Dict[str, Any] | None = None,
) -> List[Dict[str, str]]:
    system = (
        "你是标签生成器。输出必须是 JSON，且严格遵守给定 schema。"
        "标签应是学科性/方面性/总结性关键词，避免寒暄词、口头语、碎片词。"
        "优先使用短词(2~6字)和高概括词，不要输出标点、语气词或停用词。"
        "不要输出与内容无关或重复的词。"
        f"最多 {max_tags} 个标签。"
        f"schema: {json.dumps(TAG_GENERATION_SCHEMA, ensure_ascii=False)}"
    )
    prefix = [t for t in (fixed_prefix or []) if t]
    user_lines = [
        "待分析内容：",
        text,
        "固定前缀(必须保留)：",
        json.dumps(prefix, ensure_ascii=False),
        "现有 tags 池(可参考)：",
        json.dumps(tag_pool or {}, ensure_ascii=False),
        "请输出 JSON。",
    ]
    user = "\n".join(user_lines)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
