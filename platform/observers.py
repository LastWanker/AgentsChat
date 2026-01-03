class Observer:
    id: str
    scope: str  # public | group:xxx
    def on_event(self, event): ...


class AgentObserver:
    """
    让 Agent 以 Observer 的身份“看到世界”
    但不允许它立刻行动
    """
    def __init__(self, agent):
        self.agent = agent
        self.id = agent.id
        self.scope = agent.scope

    def on_event(self, event: dict):
        # Agent 只是“看见”
        self.agent.observe(event)



class ConsoleObserver:
    def on_event(self, event: dict):
        print(...)