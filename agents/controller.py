# agents/controller.py
from __future__ import annotations

from typing import List, Optional, Dict, Any
from uuid import uuid4

from events.references import ref_event_id
from events.intention_schemas import IntentionDraft
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
            memory=None,
    ):
        self.agents = agents
        self._by_id = {a.id: a for a in agents}

        self.store = store
        self.query = query
        self.memory = memory

        self.proposer = proposer or IntentionProposer(
            config=ProposerConfig(enable_llm=False)
        )
        self._latest_event: Optional[Dict[str, Any]] = None

        self.id = "agent_controller"

    # ===== World Observer 入口 =====
    def on_event(self, event: Dict[str, Any]):
        """
        世界中发生新事件时，Controller 被动接收：
        - 记录最近事件，供后续轮次提取意向草稿
        """
        etype = event.get("type")
        if not etype:
            print(
                "[agents/controller.py] ⚠️ 收到缺少 type 的事件，无法分派，已忽略：",
                event,
            )
            return

        self._latest_event = event

    def propose_for_agent(self, agent) -> Optional[IntentionDraft]:
        trigger_event = self._latest_event or self._latest_store_event()
        if not trigger_event:
            return None
        ctx = self._build_context(agent, trigger_event)
        drafts, _hints = self.proposer.propose(ctx)
        if not drafts:
            return None
        draft = drafts[0]
        draft.intention_id = draft.intention_id or str(uuid4())
        draft.agent_id = agent.id
        print(
            f"[agents/controller.py] 🧩 为 {agent.name} 生成草稿 {draft.intention_id} ({draft.kind})"
        )
        return draft

    # ===== 选人逻辑（从 legacy 迁移并扩展）=====
    def _select_agents_for_event(self, event: Dict[str, Any]) -> List:
        sender_id = event.get("sender")
        return [a for a in self.agents if a.id != sender_id]

    # ===== Context 构造 =====
    def _build_context(self, agent, trigger_event: Dict[str, Any]) -> ProposerContext:
        # 可选：给 proposer 一点“最近事件”与“引用链”
        recent = []
        referenced = []
        personal_tasks: Dict[str, Any] = {}
        tag_pool: Dict[str, Any] = {}
        team_board: List[Dict[str, Any]] = []
        if self.query is not None:
            try:
                recent_events = [e.__dict__ if hasattr(e, "__dict__") else dict(e) for e in self.query.last_n(20)]
                recent = [self._event_corpus_payload(ev) for ev in recent_events]
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
                        referenced.append(self._event_corpus_payload(ev.__dict__ if hasattr(ev, "__dict__") else dict(ev)))
            except Exception as exc:
                print(
                    f"[agents/controller.py] ⚠️ 读取引用事件失败，将忽略引用：{type(exc).__name__}:{exc}"
                )
                referenced = []
        if self.memory is not None:
            try:
                table = self.memory.personal_table_for(agent.id)
                personal_tasks = {
                    "done_list": table.done_list,
                    "todo_list": table.todo_list,
                }
            except Exception as exc:
                print(
                    f"[agents/controller.py] ⚠️ 读取个人事务表失败：{type(exc).__name__}:{exc}"
                )
            try:
                tag_pool = self.memory.tag_pool_payload()
            except Exception as exc:
                print(
                    f"[agents/controller.py] ⚠️ 读取 tags 池失败：{type(exc).__name__}:{exc}"
                )
            try:
                team_board = self._team_board_payload(self.memory.team_board_payload())
            except Exception as exc:
                print(
                    f"[agents/controller.py] ⚠️ 读取 TeamBoard 失败：{type(exc).__name__}:{exc}"
                )

        return ProposerContext(
            agent_id=agent.id,
            agent_name=getattr(agent, "name", agent.id),
            agent_role=getattr(agent, "role", None),
            agent_expertise=getattr(agent, "expertise", []) or [],
            trigger_event=trigger_event,
            store=self.store,
            memory=self.memory,
            recent_events=recent,
            referenced_events=referenced,
            personal_tasks=personal_tasks,
            tag_pool={"tags": tag_pool.get("tags", []) if tag_pool else []},
            team_board=team_board,
            agent_count=len(self.agents),
        )

    def _latest_store_event(self) -> Optional[Dict[str, Any]]:
        if self.query is None:
            return None
        recent = self.query.last_n(1)
        if not recent:
            return None
        ev = recent[0]
        return ev.__dict__ if hasattr(ev, "__dict__") else dict(ev)

    @staticmethod
    def _event_corpus_payload(event: Dict[str, Any]) -> Dict[str, Any]:
        metadata = event.get("metadata") or {}
        sender_id = str(event.get("sender", ""))
        sender_name = metadata.get("sender_name") or metadata.get("name") or event.get("sender_name")
        sender_role = metadata.get("sender_role") or metadata.get("role") or event.get("sender_role")
        sender_parts = [sender_id, sender_name, sender_role]
        sender_label = ", ".join(str(part) for part in sender_parts if part)
        content = event.get("content") or event.get("payload") or {}
        tags = list(event.get("tags") or [])
        return {"sender": sender_label, "content": content, "tags": tags}

    @staticmethod
    def _team_board_payload(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        payload: List[Dict[str, Any]] = []
        for entry in entries or []:
            payload.append(
                {
                    "kind": entry.get("kind", ""),
                    "summary": entry.get("summary", ""),
                }
            )
        return payload
