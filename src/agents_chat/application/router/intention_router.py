from __future__ import annotations

from typing import Optional

from events.types import Decision, Event, Intention, new_event
from events.store import EventStore
from agents.interpreter import IntentInterpreter


class IntentionRouter:
    """Translate approved intention to event and dispatch to world + store."""

    def __init__(
        self,
        *,
        world,
        store: EventStore,
        interpreter: IntentInterpreter,
    ) -> None:
        self.world = world
        self.store = store
        self.interpreter = interpreter

    def handle_intention(
        self, intention: Intention, agent, *, tick_index: int = 0
    ) -> Decision:
        _ = tick_index
        payload_preview = self._format_payload_preview(intention)
        decision: Decision = self.interpreter.interpret_intention(
            intention, agent, self.world, self.store
        )
        event = self._intention_to_event(intention, agent)
        self.store.append(event)
        self.world.emit(event)
        if payload_preview:
            print(
                f"[application/router] routed {intention.intention_id} -> {event.event_id}: {payload_preview}"
            )
        return decision

    @staticmethod
    def _format_payload_preview(intention: Intention) -> Optional[str]:
        payload = intention.payload or {}
        if not isinstance(payload, dict):
            return str(payload)
        for key in ("text", "content", "message"):
            if key in payload and payload[key]:
                text = str(payload[key])
                return text if len(text) <= 120 else text[:117] + "..."
        if payload:
            return str(payload)
        return None

    @staticmethod
    def _intention_to_event(intention: Intention, agent) -> Event:
        return new_event(
            sender=agent.id,
            type=intention.kind,
            content=intention.payload,
            references=intention.references,
            tags=intention.tags,
            sender_name=getattr(agent, "name", ""),
            sender_role=getattr(agent, "role", ""),
            metadata={"agent_expertise": getattr(agent, "expertise", [])},
        )

