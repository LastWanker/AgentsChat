# agents/proposer.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from events.intention_schemas import IntentionDraft, RetrievalInstruction
from llm.client import LLMRequestOptions
from llm.prompts import build_intention_prompt
from llm.schemas import parse_intention_draft
from uuid import uuid4


# ========= Context：未来 prompt 的工位 =========

@dataclass
class ProposerContext:
    agent_id: str
    agent_name: str
    agent_role: Optional[str]
    scope: Optional[str]

    trigger_event: Dict[str, Any]

    # v0.31+ 可逐步填充
    recent_events: List[Dict[str, Any]] = field(default_factory=list)
    referenced_events: List[Dict[str, Any]] = field(default_factory=list)


# ========= 给 Controller 的“软建议” =========

@dataclass(frozen=True)
class ProposerHints:
    suggest_agents: List[str] = field(default_factory=list)
    suggest_roles: List[str] = field(default_factory=list)
    notes: Optional[str] = None


# ========= 行为开关 / 未来节流位 =========

@dataclass
class ProposerConfig:
    enable_llm: bool = False        # 是否启用 LLM
    allow_speak_replies: bool = True
    llm_mode: str = "async"

    max_intentions_per_event: int = 2


# ========= 唯一对外入口 =========

class IntentionProposer:
    """
    LLM-ready Intention proposer.

    - 对外：一个类、一个 propose 接口
    - 内部：有 LLM 就用，没有就规则降级
    """

    def __init__(
        self,
        *,
        config: Optional[ProposerConfig] = None,
        llm_client: Optional[Any] = None,   # 未来注入，不强依赖
    ):
        self.config = config or ProposerConfig()
        self.llm_client = llm_client

    # ---------- 主入口 ----------

    def propose(
        self,
        context: ProposerContext,
    ) -> Tuple[List[IntentionDraft], ProposerHints]:

        if self._use_llm():
            intentions, hints = self._propose_with_llm(context)
        else:
            intentions, hints = self._propose_with_rules(context)

        intentions = self._validate_and_trim(intentions)
        return intentions, hints

    # ---------- 模式选择 ----------

    def _use_llm(self) -> bool:
        return bool(self.config.enable_llm and self.llm_client is not None)

    # ---------- 规则模式（v0.3 占位大脑） ----------

    def _propose_with_rules(
        self,
        context: ProposerContext,
    ) -> Tuple[List[IntentionDraft], ProposerHints]:

        event = context.trigger_event
        etype = event.get("type")
        event_id = event.get("event_id")
        # payload = event.get("payload") or {}
        payload = event.get("payload") or event.get("content") or {}
        event_scope = event.get("scope") or context.scope or "public"

        intentions: List[IntentionDraft] = []
        hints = ProposerHints()
        confidence, motivation, urgency = self._default_intent_scores(etype)

        if etype in ("request_anyone", "request_specific", "request_all"):
            if self._should_submit_for_request(event_scope, etype, context):
                intentions.append(
                    IntentionDraft(
                        intention_id=str(uuid4()),
                        agent_id=context.agent_id,
                        kind="submit",
                        message_plan="提交对请求的响应并引用请求链路",
                        retrieval_plan=[
                            RetrievalInstruction(
                                name="follow-request-thread",
                                after_event_id=event_id,
                                thread_depth=1,
                                scope=event_scope,
                            )
                        ],
                        target_scope=event_scope,
                        confidence=confidence,
                        motivation=motivation,
                        urgency=urgency,
                    )
                )

        elif etype in ("speak", "speak_public"):
            if self.config.allow_speak_replies:
                intentions.append(
                    IntentionDraft(
                        intention_id=str(uuid4()),
                        agent_id=context.agent_id,
                        kind="speak",
                        message_plan=self._simple_discussion_reply(payload.get("text")),
                        retrieval_plan=[
                            RetrievalInstruction(
                                name="thread", after_event_id=event_id, thread_depth=1, scope=event_scope
                            )
                        ],
                        target_scope=context.scope or event_scope,
                        confidence=confidence,
                        motivation=motivation,
                        urgency=urgency,
                    )
                )

        if not intentions:
            intentions.append(
                IntentionDraft(
                    intention_id=str(uuid4()),
                    agent_id=context.agent_id,
                    kind="speak",
                    message_plan="收到事件，暂时没有补充。",
                    retrieval_plan=[
                        RetrievalInstruction(
                            name="fallback-thread",
                            after_event_id=event_id,
                            thread_depth=1,
                            scope=event_scope,
                        )
                    ],
                    target_scope=context.scope or event_scope,
                    confidence=confidence,
                    motivation=motivation,
                    urgency=urgency,
                )
            )

        return intentions, hints

    # ---------- LLM 模式（接口已钉死，内部可自由演化） ----------

    def _propose_with_llm(
        self,
        context: ProposerContext,
    ) -> Tuple[List[IntentionDraft], ProposerHints]:
        """
        未来：
        - 构造 prompt（只用 context）
        - 要求 LLM 输出 Intention JSON
        - parse + validate
        """
        if self.llm_client is None:
            raise RuntimeError("⚠️LLM client 未注入，无法走 LLM 流程")

        messages = build_intention_prompt(
            agent_name=context.agent_name,
            agent_role=context.agent_role,
            trigger_event=context.trigger_event,
            recent_events=context.recent_events,
            referenced_events=context.referenced_events,
            phase="draft",
        )
        options = LLMRequestOptions(stream=self.config.llm_mode == "stream")

        if self.config.llm_mode == "async":
            content = asyncio.run(self.llm_client.acomplete(messages, options=options))
        elif self.config.llm_mode == "stream":
            content = "".join(self.llm_client.stream(messages, options=options))
        else:
            content = self.llm_client.complete(messages, options=options)

        try:
            draft = parse_intention_draft(content)
        except Exception as exc:  # noqa: BLE001 - LLM 输出可能不稳定
            print(
                "[agents/proposer.py] ⚠️ LLM 输出解析失败，回退规则模式：",
                f"{type(exc).__name__}: {exc}",
            )
            return self._propose_with_rules(context)

        if not draft.retrieval_plan:
            draft.retrieval_plan = [
                RetrievalInstruction(
                    name="fallback-thread",
                    after_event_id=context.trigger_event.get("event_id"),
                    thread_depth=1,
                    scope=context.trigger_event.get("scope") or context.scope,
                )
            ]
        return [draft], ProposerHints()

    # ---------- 公共校验 / 裁剪 ----------

    def _validate_and_trim(
        self,
            intentions: List[IntentionDraft],
    ) -> List[IntentionDraft]:

        # v0.3：只做最保守的裁剪
        if len(intentions) > self.config.max_intentions_per_event:
            intentions = intentions[: self.config.max_intentions_per_event]

        return intentions

    def _simple_discussion_reply(self, text: Optional[str]) -> str:
        if text:
            return f"收到发言，基于实时时间冷却后给出讨论：{text}"
        return "收到发言，基于实时时间冷却后给出讨论意见。"

    def _default_intent_scores(self, etype: Optional[str]) -> Tuple[float, float, float]:
        if etype in ("request_anyone", "request_specific", "request_all"):
            return 0.5, 0.8, 0.8
        if etype in ("speak", "speak_public"):
            return 0.6, 0.4, 0.3
        return 0.4, 0.4, 0.2

    def _should_submit_for_request(
            self, event_scope: str, etype: str, context: ProposerContext
    ) -> bool:
        if etype == "request_all":
            if self._is_boss(context):
                return False
            if event_scope != "public" and context.scope != event_scope:
                return False
        return True

    def _is_boss(self, context: ProposerContext) -> bool:
        for value in (context.agent_role, context.agent_name, context.agent_id):
            if value and str(value).upper() == "BOSS":
                return True
        return False