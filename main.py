from platform.world import World
from agents.agent import Agent

world = World()


class DebugObserver:
    def on_event(self, event):
        print(event["type"], event["content"])


world.add_observer(DebugObserver())

a = Agent("Alice", "thinker", ["logic"])
b = Agent("Bob", "critic", ["debate"])

e1 = a.speak_public("世界是圆的")
world.emit(e1)

e2 = b.speak_public("你这个结论没有论证", references=[e1["event_id"]])
world.emit(e2)
