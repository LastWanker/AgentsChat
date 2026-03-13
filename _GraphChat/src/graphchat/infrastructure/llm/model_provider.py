from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable

from graphchat.domain.models.planning_schema import (
    ActionPlanOutput,
    DEFAULT_ACTION_PRIORITY,
    normalize_actions_v2,
)


def _ensure_scope(payload: dict) -> dict:
    data = dict(payload)
    if "world_scope" not in data:
        data["world_scope"] = "group:main"
    return data


class RuleBasedModelProvider:
    """规则模型：无外部依赖，作为稳定兜底。"""

    def _build_v2_result(
        self,
        *,
        actions: list[dict],
        task_done: bool = False,
        reasoning_summary: str = "rule_based_fallback",
    ) -> dict:
        normalized = normalize_actions_v2(actions=actions)
        # V1 兼容：过渡期继续输出 action/payload 供旧节点读取。
        if normalized:
            first = normalized[0]
            action = str(first.get("action_id") or "listen_only")
            payload = _ensure_scope(first.get("payload", {}))
        else:
            action = "listen_only"
            payload = _ensure_scope({"reason": "empty_actions"})
        return {
            "plan_version": "v2",
            "reasoning_summary": reasoning_summary,
            "task_done": bool(task_done),
            "actions": normalized,
            "action": action,  # V1 兼容
            "payload": payload,  # V1 兼容
        }

    def plan_action(self, state: dict) -> dict:
        last_text = str(state.get("last_event", {}).get("payload", {}).get("text", ""))
        text = str(state.get("action_payload", {}).get("text") or last_text)

        if "投票" in text:
            return self._build_v2_result(
                actions=[
                    {
                        "action_id": "vote_decision",
                        "plan_text": "[vote] 发起投票并收集回复",
                        "payload": _ensure_scope({"text": text}),
                        "target_scope": "group:main",
                        "target_agents": [],
                        "priority": DEFAULT_ACTION_PRIORITY.get("vote_decision", 30),
                        "can_skip": False,
                        "step_index": 1,
                    }
                ],
            )
        if "解散群" in text:
            return self._build_v2_result(
                actions=[
                    {
                        "action_id": "dissolve_group",
                        "plan_text": "[governance] 发起解散群流程",
                        "payload": _ensure_scope({"text": text}),
                        "target_scope": "group:main",
                        "target_agents": [],
                        "priority": DEFAULT_ACTION_PRIORITY.get("dissolve_group", 30),
                        "can_skip": False,
                        "step_index": 1,
                    }
                ],
            )
        if "删除任务" in text:
            return self._build_v2_result(
                actions=[
                    {
                        "action_id": "maintain_board",
                        "plan_text": "[board] 删除任务",
                        "payload": _ensure_scope({"board_op": "delete", "text": text}),
                        "target_scope": "group:main",
                        "target_agents": [],
                        "priority": DEFAULT_ACTION_PRIORITY.get("maintain_board", 10),
                        "can_skip": False,
                        "step_index": 1,
                    }
                ],
            )
        if "归档任务" in text:
            return self._build_v2_result(
                actions=[
                    {
                        "action_id": "maintain_board",
                        "plan_text": "[board] 归档任务",
                        "payload": _ensure_scope({"board_op": "archive", "text": text}),
                        "target_scope": "group:main",
                        "target_agents": [],
                        "priority": DEFAULT_ACTION_PRIORITY.get("maintain_board", 10),
                        "can_skip": False,
                        "step_index": 1,
                    }
                ],
            )
        if "任务板" in text or "记录板" in text:
            return self._build_v2_result(
                actions=[
                    {
                        "action_id": "maintain_board",
                        "plan_text": "[board] 更新任务板",
                        "payload": _ensure_scope({"board_op": "upsert", "text": text}),
                        "target_scope": "group:main",
                        "target_agents": [],
                        "priority": DEFAULT_ACTION_PRIORITY.get("maintain_board", 10),
                        "can_skip": False,
                        "step_index": 1,
                    }
                ],
            )
        if "查" in text or "检索" in text:
            return self._build_v2_result(
                actions=[
                    {
                        "action_id": "search_web",
                        "plan_text": "[speak] 先检索再回应",
                        "payload": _ensure_scope({"text": text}),
                        "target_scope": "group:main",
                        "target_agents": [],
                        "priority": 25,
                        "can_skip": False,
                        "step_index": 1,
                    }
                ],
            )
        return self._build_v2_result(
            actions=[
                {
                    "action_id": "speak",
                    "plan_text": "[speak] 常规回应",
                    "payload": _ensure_scope({"text": f"收到：{text}"}),
                    "target_scope": "group:main",
                    "target_agents": [],
                    "priority": DEFAULT_ACTION_PRIORITY.get("speak", 20),
                    "can_skip": False,
                    "step_index": 1,
                }
            ]
        )


@dataclass
class LangChainStructuredModelProvider:
    """优先使用 LangChain 结构化输出，失败时自动回退规则模型。"""

    llm: object
    allowed_actions: set[str]
    fallback: RuleBasedModelProvider

    def __post_init__(self) -> None:
        # 官方推荐：chat model + with_structured_output(schema)
        self._structured_llm = self.llm.with_structured_output(ActionPlanOutput)

    def plan_action(self, state: dict) -> dict:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except Exception:
            return self.fallback.plan_action(state)

        last_text = str(state.get("last_event", {}).get("payload", {}).get("text", ""))
        visible = list(state.get("visible_events", []))[-5:]
        context = "\n".join(
            f"- {e.get('event_id', '?')}: {str(e.get('payload', {}).get('text', ''))[:120]}"
            for e in visible
        )
        allowed = ", ".join(sorted(self.allowed_actions))
        messages = [
            SystemMessage(
                content=(
                    "你是群聊代理的动作规划器（V2）。"
                    f"可用动作集合：{allowed}。"
                    "必须输出 JSON 结构，字段为 reasoning_summary、task_done、actions。"
                    "actions 是步骤列表，最多 6 步，允许重复动作。"
                    "每步必须包含 action_id、plan_text、payload、target_scope、target_agents、priority、can_skip。"
                    "建议同时给出 step_id、depends_on、dispatch(auto/serial/parallel)、step_index。"
                    "rag 也是 skill，可作为独立 action_id 出现。"
                    "默认优先级是 rag>board>speak>governance，但若给了 depends_on/step_index，以计划为准。"
                    "payload 至少要包含 world_scope。"
                )
            ),
            HumanMessage(
                content=(
                    f"最新输入: {last_text}\n"
                    f"最近可见事件:\n{context}\n"
                    "请给出下一步动作。"
                )
            ),
        ]
        try:
            parsed = self._structured_llm.invoke(messages)
        except Exception:
            return self.fallback.plan_action(state)

        task_done = bool(getattr(parsed, "task_done", False))
        reasoning_summary = str(getattr(parsed, "reasoning_summary", "") or "")
        actions_attr = getattr(parsed, "actions", None)
        action_rows: list[dict] = []
        if isinstance(actions_attr, list):
            for item in actions_attr:
                if isinstance(item, dict):
                    action_rows.append(item)
                elif hasattr(item, "model_dump"):
                    action_rows.append(item.model_dump())

        # V1 兼容输入：若模型仍给 action/payload，则包装为单步 actions[]。
        if not action_rows:
            action = str(getattr(parsed, "action", "") or "")
            payload = getattr(parsed, "payload", {}) or {}
            if action and action in self.allowed_actions:
                if not isinstance(payload, dict):
                    payload = {}
                action_rows = [
                    {
                        "action_id": action,
                        "plan_text": "[compat] single action from V1 schema",
                        "payload": _ensure_scope(payload),
                        "target_scope": "group:main",
                        "target_agents": [],
                        "priority": DEFAULT_ACTION_PRIORITY.get(action, 100),
                        "can_skip": False,
                        "step_index": 1,
                    }
                ]

        normalized = normalize_actions_v2(actions=action_rows, allowed_actions=self.allowed_actions)
        if not normalized and not task_done:
            return self.fallback.plan_action(state)
        if normalized:
            first = normalized[0]
            action = str(first.get("action_id") or "listen_only")
            payload = _ensure_scope(first.get("payload", {}))
        else:
            action = "listen_only"
            payload = _ensure_scope({"reason": "task_done_without_actions"})
        return {
            "plan_version": "v2",
            "reasoning_summary": reasoning_summary,
            "task_done": task_done,
            "actions": normalized,
            "action": action,  # V1 兼容
            "payload": payload,  # V1 兼容
        }


def _is_deepseek_target(model_name: str, model_provider: str | None) -> bool:
    provider = str(model_provider or "").strip().lower()
    return provider == "deepseek" or model_name.strip().lower().startswith("deepseek")


def _build_deepseek_llm(model_name: str):
    api_key = (
        os.getenv("GRAPHCHAT_DEEPSEEK_API_KEY", "").strip()
        or os.getenv("DEEPSEEK_API_KEY", "").strip()
    )
    base_url = os.getenv("GRAPHCHAT_DEEPSEEK_BASE_URL", "").strip()
    if api_key and not os.getenv("DEEPSEEK_API_KEY"):
        os.environ["DEEPSEEK_API_KEY"] = api_key

    # 首选 LangChain DeepSeek 官方适配。
    try:
        from langchain_deepseek import ChatDeepSeek
    except Exception:
        ChatDeepSeek = None  # type: ignore[assignment]
    if ChatDeepSeek is not None:
        try:
            kwargs = {"model": model_name, "temperature": 0}
            if api_key:
                kwargs["api_key"] = api_key
            if base_url:
                kwargs["base_url"] = base_url
            return ChatDeepSeek(**kwargs)
        except Exception:
            pass

    # 回退 OpenAI 兼容入口（DeepSeek 官方支持 OpenAI SDK 兼容模式）。
    try:
        from langchain_openai import ChatOpenAI
    except Exception:
        return None

    try:
        kwargs = {
            "model": model_name,
            "temperature": 0,
            "base_url": base_url or "https://api.deepseek.com",
        }
        if api_key:
            kwargs["api_key"] = api_key
        return ChatOpenAI(**kwargs)
    except Exception:
        return None


def build_model_provider(
    *,
    allowed_actions: Iterable[str],
    fallback: RuleBasedModelProvider | None = None,
) -> object:
    fallback = fallback or RuleBasedModelProvider()
    model_name = os.getenv("GRAPHCHAT_MODEL", "").strip()
    model_provider = os.getenv("GRAPHCHAT_MODEL_PROVIDER", "").strip() or None
    if not model_name:
        return fallback

    if _is_deepseek_target(model_name=model_name, model_provider=model_provider):
        llm = _build_deepseek_llm(model_name=model_name)
        if llm is None:
            return fallback
        try:
            return LangChainStructuredModelProvider(
                llm=llm,
                allowed_actions=set(allowed_actions),
                fallback=fallback,
            )
        except Exception:
            return fallback

    try:
        from langchain.chat_models import init_chat_model
    except Exception:
        return fallback

    try:
        llm = init_chat_model(
            model=model_name,
            model_provider=model_provider,
            temperature=0,
        )
    except Exception:
        return fallback

    try:
        return LangChainStructuredModelProvider(
            llm=llm,
            allowed_actions=set(allowed_actions),
            fallback=fallback,
        )
    except Exception:
        return fallback


# 兼容旧名称，避免外部调用断裂。
PlaceholderModelProvider = RuleBasedModelProvider
