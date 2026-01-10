from __future__ import annotations

from typing import Iterable, List, Optional

from events.references import ref_event_id
from events.store import EventStore
from events.types import Event
from events.session_memory import SessionMemory


class RequestCompletionObserver:
    """Watch submit events and close request_* once条件达成.

    一旦判定完成，会：
    - 更新原 request 事件的 completed 标记
    - 更新 team_board 记录完成摘要
    """

    id = "request_completion_observer"
    scope = "public"

    def __init__(
        self,
        *,
        store: EventStore,
        agents: List,
        memory: Optional[SessionMemory] = None,
    ):
        self.store = store
        self.agents = agents
        self.memory = memory

    # ===== Observer 接口 =====
    def on_event(self, event: dict):
        if event.get("type") != "submit":
            return

        refs = event.get("references") or []
        for ref in refs:
            self._maybe_complete_request(ref_event_id(ref))

    # ===== 核心逻辑 =====
    def _maybe_complete_request(self, request_id: str) -> None:
        request = self.store.get(request_id)
        if request is None:
            print(
                f"[platform/request_tracker.py] ⚠️ 未找到被引用的 request {request_id}，跳过。"
            )
            return

        if request.type not in {"request_anyone", "request_all", "request_specific"}:
            return

        if getattr(request, "completed", False):
            print(
                f"[platform/request_tracker.py] ℹ️ request {request_id} 已标记 completed，忽略重复检查。"
            )
            return

        submits = self._submits_referencing(request_id)
        if not submits:
            return

        ready = False
        if request.type == "request_anyone":
            ready = True
        elif request.type == "request_all":
            ready = self._all_scope_agents_submitted(request.scope, submits)
        elif request.type == "request_specific":
            ready = self._all_recipients_submitted(request.recipients, submits)

        if not ready:
            return

        self.store.mark_completed(request.event_id)
        self._record_completion(request, submits)

    # ===== 判定子逻辑 =====
    def _submits_referencing(self, request_id: str) -> List[Event]:
        results: List[Event] = []
        for ev in self.store.all():
            if ev.type != "submit":
                continue
            refs = getattr(ev, "references", []) or []
            if any(ref_event_id(r) == request_id for r in refs):
                results.append(ev)
        return results

    def _all_scope_agents_submitted(self, scope: str, submits: Iterable[Event]) -> bool:
        senders = {ev.sender for ev in submits}
        participants = {a.id for a in self.agents if getattr(a, "scope", None) == scope}
        if not participants:
            print(
                f"[platform/request_tracker.py] ⚠️ request scope {scope} 没有可匹配的参与者，无法完成。"
            )
            return False
        missing = participants - senders
        if missing:
            print(
                f"[platform/request_tracker.py] ⏳ request scope {scope} 仍缺少提交者：{missing}。"
            )
            return False
        return True

    def _all_recipients_submitted(self, recipients: List[str], submits: Iterable[Event]) -> bool:
        if not recipients:
            print("[platform/request_tracker.py] ⚠️ request_specific 缺少 recipients，无法完成。")
            return False
        senders = {ev.sender for ev in submits}
        missing = set(recipients) - senders
        if missing:
            print(
                f"[platform/request_tracker.py] ⏳ request_specific 仍缺少提交者：{missing}。"
            )
            return False
        return True

    # ===== 完成后的广播 =====
    def _record_completion(self, request: Event, submits: List[Event]) -> None:
        submit_ids = [ev.event_id for ev in submits]
        summary = self._summarize_submit_stances(request, submits)
        text = (
            f"{request.type} {request.event_id} 已被提交完成（{len(submit_ids)} 次 submit）。{summary}"
        )
        if self.memory is None:
            print(
                "[platform/request_tracker.py] ℹ️ 未配置 SessionMemory，跳过 team_board 更新。"
            )
            return
        event_ids = [request.event_id, *submit_ids]
        self.memory.add_team_board_entry(
            summary=text,
            event_ids=event_ids,
            kind="request_completion",
        )
        print(
            f"[platform/request_tracker.py] 🎉 request {request.event_id} 已闭合，更新 team_board。"
        )

    def _summarize_submit_stances(self, request: Event, submits: List[Event]) -> str:
        request_text = ""
        if isinstance(request.content, dict):
            req = request.content.get("request")
            if req:
                request_text = f"，针对请求：{req}"

        agent_names = {getattr(a, "id", None): getattr(a, "name", None) for a in self.agents}

        parts: List[str] = []
        total_stance = 0.0
        for submit in submits:
            stance = self._extract_stance(submit.references, request.event_id)
            total_stance += stance
            name = agent_names.get(submit.sender) or submit.sender
            parts.append(f"执行者：{name}（stance: {stance:+.1f}）")

        verdict = "通过词条" if total_stance > 0 else "未通过词条"
        participants = "；".join(parts) if parts else "执行者未知"
        return f"{participants}；最终得分：{total_stance:+.1f}；{verdict}{request_text}。"

    def _extract_stance(self, references: List, target_id: str) -> float:
        for ref in references or []:
            if ref_event_id(ref) != target_id:
                continue
            weight = getattr(ref, "weight", None) or ref.get("weight") if isinstance(ref, dict) else None
            if isinstance(weight, dict) and weight.get("stance") is not None:
                return float(weight.get("stance"))
        return 0.0
