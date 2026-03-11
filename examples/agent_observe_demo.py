import _bootstrap  # noqa: F401

from agents_chat.domain import Agent
from agents_chat.interfaces.event_bus.world_bus import WorldBus
from agents_chat.interfaces.observers.agent_observer import AgentObserver

world = WorldBus()

alice = Agent("Alice", "thinker", ["logic"])
bob = Agent("Bob", "critic", ["debate"])

world.add_observer(AgentObserver(alice))
world.add_observer(AgentObserver(bob))

e1 = alice.speak("The world is round.")
world.emit(e1)

e2 = bob.speak("Need stronger evidence.", references=[e1["event_id"]])
world.emit(e2)

print("Alice memory:", alice.memory)
print("Bob memory:", bob.memory)
print("World events:", len(world.events))
