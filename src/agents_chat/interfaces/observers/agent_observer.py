class AgentObserver:
    def __init__(self, agent):
        self.agent = agent

    @property
    def id(self):
        return self.agent.id

    def on_event(self, event: dict):
        self.agent.observe(event)

