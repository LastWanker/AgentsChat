from typing import Optional
from events.types import Intention, Decision, new_event, Event
from events.store import EventStore


class Router:
    """
    把 approved 的 intention 定型为 Event，然后交给 World/Store。
    这里不做智能推理，只做翻译与投递。
    """
    def __init__(self, world, store: EventStore, interpreter):
        self.world = world
        self.store = store
        self.interpreter = interpreter

    def handle_intention(self, intention: Intention, agent) -> Decision:
        decision: Decision = self.interpreter.interpret_intention(intention, agent, self.world, self.store)
        if decision.status != "approved":
            intention.status = "suppressed"
            return decision

        event = self._intention_to_event(intention, agent)
        self.store.append(event)
        # self.world.emit(event.__dict__)  # 兼容你现有 World.emit(dict)
        self.world.emit(event)
        intention.status = "executed"
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
