class World:
    def __init__(self):
        self.agents = {}

    def register(self, agent):
        ...

    def emit(self, event: dict):
        ...
