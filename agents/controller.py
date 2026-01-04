from typing import List, Optional
from uuid import uuid4
from events.types import Intention

class AgentController:
    """
    v0：先别上 LLM。用“脚本式意向”跑通闭环。
    """
    def __init__(self, agents: List):
        self.agents = agents
        self._queue: List[Intention] = []

    def seed_demo_intentions(self):
        # demo：让第一个 agent 产生一条 speak
        a = self.agents[0]
        it = Intention(
            intention_id=str(uuid4()),
            agent_id=a.id,
            kind="speak",
            payload={"text": "我是 {a.name}，系统开始跑了。"},
            scope=a.scope,
            references=[],
            completed=True,
            urgency=0.1,
        )
        self._queue.append(it)

    def pending(self) -> List[Intention]:
        return [x for x in self._queue if x.status == "pending"]

    def pop_one(self) -> Optional[Intention]:
        for x in self._queue:
            if x.status == "pending":
                return x
        return None
