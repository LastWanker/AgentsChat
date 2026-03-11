import _bootstrap  # noqa: F401

from agents_chat.domain import Agent
from agents_chat.interfaces.event_bus.world_bus import WorldBus
from agents_chat.interfaces.observers.agent_observer import AgentObserver

world = WorldBus()
a = Agent("Alice", "thinker", ["logic"])
b = Agent("Bob", "critic", ["debate"])

world.add_observer(AgentObserver(a))
world.add_observer(AgentObserver(b))

first = a.speak("Question: is this assumption valid?")
world.emit(first)
second = b.speak("Counterpoint with reference.", references=[first["event_id"]])
world.emit(second)

print("events in world:", len(world.events))
print("event ids:", [ev.get("event_id") for ev in world.events])
