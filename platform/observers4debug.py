class DebugObserver4world_v01:
    def on_event(self, event):
        print(event["type"], event["content"])


class DebugObserver4world_v02:
    def __init__(self, name, scope="public"):
        self.name = name
        self.scope = scope

    def on_event(self, event):
        print(f"[{self.name} sees] {event['type']} | {event['content']}")
