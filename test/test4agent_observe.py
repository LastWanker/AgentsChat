from platform.world import World
from platform.observers import AgentObserver
from agents.agent import Agent

world = World()

a = Agent("Alice", "thinker", ["logic"])
b = Agent("Bob", "critic", ["debate"])

# 让 Agent “看世界”
world.add_observer(AgentObserver(a))
world.add_observer(AgentObserver(b))

# Alice 先说话
e1 = a.speak("世界是圆的")
world.emit(e1)

# Bob 再说话
e2 = b.speak("你这个结论没有论证", references=[e1["event_id"]])
world.emit(e2)

# ====== 断言（现在可以是 print） ======

print("Alice memory:", a.memory)
print("Bob memory:", b.memory)
print("World events:", len(world.events))
