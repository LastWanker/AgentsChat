from typing import Optional

from events.types import Intention, Decision, new_event, Event
from events.store import EventStore
from agents.interpreter import IntentInterpreter


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
    ):
        self.world = world
        self.store = store
        self.interpreter = interpreter

    def handle_intention(self, intention: Intention, agent, *, tick_index: int = 0) -> Decision:
        payload_preview = self._format_payload_preview(intention)
        print(
            f"[platform/router.py] 📨 收到 {agent.name} 的意向 {intention.intention_id}，先让解释器看看。"
            + (f" payload: {payload_preview}" if payload_preview else "")
        )
        decision: Decision = self.interpreter.interpret_intention(intention, agent, self.world, self.store)

        event = self._intention_to_event(intention, agent)
        print(
            f"[platform/router.py] ✅ 意向 {intention.intention_id} 通过，转换成事件 {event.event_id}，准备广播。"
            + (f" payload: {payload_preview}" if payload_preview else "")
        )
        self.store.append(event)
        # self.world.emit(event.__dict__)  # 兼容你现有 World.emit(dict)
        self.world.emit(event)
        print(f"[platform/router.py] 📣 事件 {event.event_id} 已送入世界，大家随意围观。")
        return decision

    def _format_payload_preview(self, intention: Intention) -> Optional[str]:
        payload = intention.payload or {}
        if not isinstance(payload, dict):
            return str(payload)
        for key in ("text", "content", "message"):
            if key in payload and payload[key]:
                value = payload[key]
                text = str(value)
                return text if len(text) <= 120 else text[:117] + "..."
        if payload:
            return str(payload)
        return None

    def _intention_to_event(self, intention: Intention, agent) -> Event:
        # 最小映射：kind -> event.type, payload -> content
        return new_event(
            sender=agent.id,
            type=intention.kind,
            content=intention.payload,
            references=intention.references,
            tags=intention.tags,
            metadata={
                "sender_name": getattr(agent, "name", ""),
                "sender_role": getattr(agent, "role", ""),
            },
        )
