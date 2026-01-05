import time
from typing import Dict, Optional, Tuple, List

from events.types import Intention, Decision, new_event, Event
from events.store import EventStore
from agents.interpreter import IntentInterpreter


class CooldownGuard:
    """在 Router 层做基础节流：既看轮次又看时间。"""

    def __init__(self, cooldowns_sec: Optional[Dict[str, float]] = None, *, inter_event_gap_sec: float = 0.0):
        self.cooldowns_sec = cooldowns_sec or {}
        self.inter_event_gap_sec = inter_event_gap_sec
        self._last_tick_by_agent: Dict[str, int] = {}
        self._last_time_by_agent: Dict[str, float] = {}
        self._last_event_time: Optional[float] = None

    def allow(self, agent_id: str, tick_index: int, now: Optional[float] = None) -> Tuple[bool, List[Dict[str, str]]]:
        """返回 (是否通过, violations)。"""
        now = now if now is not None else time.monotonic()
        violations: List[Dict[str, str]] = []

        last_tick = self._last_tick_by_agent.get(agent_id)
        if last_tick is not None and tick_index - last_tick < 1:
            violations.append({"kind": "cooldown", "rule": "round_gap", "detail": "need wait next tick"})

        cd_sec = self.cooldowns_sec.get(agent_id, 0.0)
        last_time = self._last_time_by_agent.get(agent_id)
        if cd_sec > 0 and last_time is not None:
            elapsed = now - last_time
            if elapsed < cd_sec:
                violations.append(
                    {"kind": "cooldown", "rule": "self_time", "detail": f"wait {cd_sec - elapsed:.2f}s"}
                )

        if self.inter_event_gap_sec > 0 and self._last_event_time is not None:
            gap_elapsed = now - self._last_event_time
            if gap_elapsed < self.inter_event_gap_sec:
                violations.append(
                    {"kind": "cooldown", "rule": "after_event", "detail": f"wait {self.inter_event_gap_sec - gap_elapsed:.2f}s"}
                )

        return len(violations) == 0, violations

    def record_success(self, agent_id: str, tick_index: int, now: Optional[float] = None):
        now = now if now is not None else time.monotonic()
        self._last_tick_by_agent[agent_id] = tick_index
        self._last_time_by_agent[agent_id] = now
        self._last_event_time = now


class Router:
    """
    把 approved 的 intention 定型为 Event，然后交给 World/Store。
    这里不做智能推理，只做翻译与投递。
    解释器入口唯一：只接受 agents/interpreter.py 的 IntentInterpreter。
    """

    def __init__(
            self,
            world,
            store: EventStore,
            interpreter: IntentInterpreter,
            *,
            cooldowns_sec: Optional[Dict[str, float]] = None,
            inter_event_gap_sec: float = 0.0,
    ):
        self.world = world
        self.store = store
        self.interpreter = interpreter
        self.cooldown_guard = CooldownGuard(cooldowns_sec, inter_event_gap_sec=inter_event_gap_sec)

        def handle_intention(self, intention: Intention, agent, *, tick_index: int = 0) -> Decision:
            now = time.monotonic()
            allow, cooldown_violations = self.cooldown_guard.allow(agent.id, tick_index, now=now)
            if not allow:
                print(
                    f"[platform/router.py] ⏳ {agent.name} 的意向 {intention.intention_id} 触发 cooldown，暂不处理。"
                )
                intention.status = "suppressed"
                return Decision(status="suppressed", violations=cooldown_violations)
            print(
                f"[platform/router.py] 📨 收到 {agent.name} 的意向 {intention.intention_id}，先让解释器看看。"
            )
            decision: Decision = self.interpreter.interpret_intention(intention, agent, self.world, self.store)
            if decision.status != "approved":
                print(
                    f"[platform/router.py] 🚫 意向 {intention.intention_id} 没过审，状态是 {decision.status}，先压下去。"
                )
                intention.status = "suppressed"
                return decision

            event = self._intention_to_event(intention, agent)
            print(
                f"[platform/router.py] ✅ 意向 {intention.intention_id} 通过，转换成事件 {event.event_id}，准备广播。"
            )
            self.store.append(event)
            # self.world.emit(event.__dict__)  # 兼容你现有 World.emit(dict)
            self.world.emit(event)
            intention.status = "executed"
            self.cooldown_guard.record_success(agent.id, tick_index, now=now)
            print(f"[platform/router.py] 📣 事件 {event.event_id} 已送入世界，大家随意围观。")
            return decision

    def _intention_to_event(self, intention: Intention, agent) -> Event:
        # 最小映射：kind -> event.type, payload -> content
        return new_event(
            sender=agent.id,
            type=intention.kind,
            scope=intention.scope,
            content=intention.payload,
            references=intention.references,
            completed=intention.completed,
        )
