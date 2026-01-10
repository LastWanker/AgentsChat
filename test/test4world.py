from platform.world import World
from agents.agent import Agent
from platform.observers4debug import DebugObserver4world_v02, DebugObserver4world_v01

world = World()


print("test4world_v01")
world.add_observer(DebugObserver4world_v01())
a = Agent("Alice", "thinker", ["logic"])
b = Agent("Bob", "critic", ["debate"])
e1 = a.speak("世界是圆的")
world.emit(e1)
e2 = b.speak("你这个结论没有论证", references=[e1["event_id"]])
world.emit(e2)

print("test4world_v02")
world.add_observer(DebugObserver4world_v02("ALL"))
world.add_observer(DebugObserver4world_v02("GROUP_A"))
