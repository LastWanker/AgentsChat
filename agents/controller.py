# agents/controller.py
from __future__ import annotations

from typing import List, Optional, Dict, Any
from uuid import uuid4

from events.references import ref_event_id
from events.types import Intention
from agents.proposer import IntentionProposer, ProposerContext, ProposerConfig


class AgentController:
    """
    只负责观察 -> 产生意向 -> 入队，绝不直接向 World emit 事件。
    """

    def __init__(
            self,
            agents: List,
            *,
            proposer: Optional[IntentionProposer] = None,
            store=None,  # EventStore，可选：用来给 proposer 喂 recent/ref
            query=None,  # EventQuery，可选
    ):
        self.agents = agents
        self._by_id = {a.id: a for a in agents}
        self._queue: List[Intention] = []

        self.store = store
        self.query = query

        self.proposer = proposer or IntentionProposer(
            config=ProposerConfig(enable_llm=False)
        )

        # 让 Controller 作为 observer 时具备“看见一切”的权限
        self.id = "agent_controller"
        self.scope = "public"

    # ===== World Observer 入口 =====
    def on_event(self, event: Dict[str, Any]):
        """
        世界中发生新事件时，Controller 被动接收：
        - 判断是否需要响应
        - 选出合适的 agent（或多个）
        - 为每个 agent 调 proposer 产出 intentions
        - 入队
        """
        etype = event.get("type")
        if not etype:
            print(
                "[agents/controller.py] ⚠️ 收到缺少 type 的事件，无法分派，已忽略：",
                event,
            )
            return

        # 只对未 completed 的 request 做响应（沿用 legacy 语义）
        if etype in ("request_anyone", "request_specific") and event.get("completed", True):
            print(
                f"[agents/controller.py] ⚠️ 事件 {event.get('event_id', '<no-id>')} 已完成，跳过响应。"
            )
            return

        candidates = self._select_agents_for_event(event)
        if not candidates:
            print(
                f"[agents/controller.py] ⚠️ 事件 {event.get('event_id', '<no-id>')} 没有合适的 Agent 响应，暂不处理。"
            )
            return

        for agent in candidates:
            ctx = self._build_context(agent, event)
            intentions, _hints = self.proposer.propose(ctx)
            for it in intentions:
                self._queue.append(it)
                print(
                    f"[agents/controller.py] 🧩 收到事件 {event.get('event_id')}，为 {agent.name} 入队意向 {it.intention_id} ({it.kind})"
                )

    # ===== 选人逻辑（从 legacy 迁移并扩展）=====
    def _select_agents_for_event(self, event: Dict[str, Any]) -> List:
        etype = event.get("type")
        sender_id = event.get("sender")
        scope = event.get("scope", "public")

        # ---- request_specific：必须是 recipients ----
        if etype == "request_specific":
            recipients = event.get("recipients") or []
            # 只挑收件人里真实存在、并且看得见该事件的
            picked = []
            for rid in recipients:
                a = self._by_id.get(rid)
                if a and self._is_visible(scope, a.scope):
                    picked.append(a)
            return picked

        # ---- request_anyone：排除 sender，所有符合可见性的 Agent 都可响应 ----
        if etype == "request_anyone":
            cands = [
                a for a in self.agents
                if a.id != sender_id and self._is_visible(scope, a.scope)
            ]
            return cands

        # 默认：其它事件不派生（避免刷屏）
        return []

    def _is_visible(self, event_scope: str, agent_scope: str) -> bool:
        # 对齐 World._is_visible 的核心语义
        if event_scope == "public":
            return True
        if agent_scope == "public":
            return True
        return event_scope == agent_scope

    # ===== Context 构造 =====
    def _build_context(self, agent, trigger_event: Dict[str, Any]) -> ProposerContext:
        # 可选：给 proposer 一点“最近事件”与“引用链”
        recent = []
        referenced = []
        if self.query is not None:
            try:
                recent = [e.__dict__ if hasattr(e, "__dict__") else dict(e) for e in self.query.last_n(20)]
            except Exception as exc:
                print(
                    f"[agents/controller.py] ⚠️ 获取最近事件失败，将使用空列表：{type(exc).__name__}:{exc}"
                )
                recent = []

        if self.store is not None:
            try:
                refs = trigger_event.get("references") or []
                for r in refs[:10]:
                    ev = self.store.get(ref_event_id(r))
                    if ev:
                        referenced.append(ev.__dict__ if hasattr(ev, "__dict__") else dict(ev))
            except Exception as exc:
                print(
                    f"[agents/controller.py] ⚠️ 读取引用事件失败，将忽略引用：{type(exc).__name__}:{exc}"
                )
                referenced = []

        return ProposerContext(
            agent_id=agent.id,
            agent_name=getattr(agent, "name", agent.id),
            agent_role=getattr(agent, "role", None),
            scope=getattr(agent, "scope", "public"),
            trigger_event=trigger_event,
            recent_events=recent,
            referenced_events=referenced,
        )

    # ===== 队列接口 =====
    def pending(self) -> List[Intention]:
        return [x for x in self._queue if x.status == "pending"]

    def prune_done(self) -> None:
        """把已执行/被压制的意向移出队列，避免影响队列状态判断。"""

        before = len(self._queue)
        self._queue = [x for x in self._queue if x.status == "pending"]
        if len(self._queue) != before:
            print(
                f"[agents/controller.py] 🧹 清理了 {before - len(self._queue)} 条已完成/被压制的意向，剩余 {len(self._queue)} 条待处理。"
            )

    def pop_one(self) -> Intention | None:
        for x in self._queue:
            if x.status == "pending":
                print(
                    f"[agents/controller.py] 📬 发现排队的意向 {x.intention_id}，准备交给调度器。"
                )
                return x
        print("[agents/controller.py] 🧘 队列空了。")
        return None

    def seed_demo_intentions(self):
        # demo：让第一个 agent 产生一条 speak
        a = self.agents[0]
        it = Intention(
            intention_id=str(uuid4()),
            agent_id=a.id,
            kind="speak",
            payload={"text": f"我是 {a.name}，系统开始跑了。"},
            scope=a.scope,
            candidate_references=[],
            references=[],
            completed=True,
            urgency=0.1,
        )
        self._queue.append(it)
        print(
            f"[agents/controller.py] 🎤 给 {a.name} 塞了一条初始意向 {it.intention_id}，模拟让第一个 agent 产生一条 speak。"
        )
