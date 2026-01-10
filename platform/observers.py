class Observer:
    id: str

    def on_event(self, event): ...


class AgentObserver:
    """
    让 Agent 以 Observer 的身份“看到世界”
    但不允许它立刻行动
    """

    def __init__(self, agent):
        self.agent = agent
        # self.id = agent.id

    @property
    def id(self):
        return self.agent.id

    def on_event(self, event: dict):
        # Agent 只是“看见”
        self.agent.observe(event)


class ConsoleObserver:
    def on_event(self, event: dict):
        sender = event.get("sender", "?")
        etype = event.get("type", "<unknown>")
        content = event.get("content", {})
        print(f"{etype} from {sender}: {content}")
