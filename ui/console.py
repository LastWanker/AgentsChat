class ConsoleUI:
    def __init__(self, store):
        self.store = store

    def render_last(self, n: int = 20):
        evs = self.store.all()[-n:]
        for e in evs:
            print(f"[{e.timestamp}] ({e.scope}) {e.type} from {e.sender}: {e.content}")
