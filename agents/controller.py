from typing import List
from uuid import uuid4
from events.types import Intention


class AgentController:
    """
    只负责观察 -> 产生意向 -> 入队，绝不直接向 World emit 事件。
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
            payload={"text": f"我是 {a.name}，系统开始跑了。"},
            scope=a.scope,
            references=[],
            completed=True,
            urgency=0.1,
        )
        self._queue.append(it)
        print(
            f"[agents/controller.py] 🎤 给 {a.name} 塞了一条初始意向 {it.intention_id}，模拟让第一个 agent 产生一条 speak。"
        )

    def pending(self) -> List[Intention]:
        return [x for x in self._queue if x.status == "pending"]

    def pop_one(self) -> Intention | None:
        for x in self._queue:
            if x.status == "pending":
                print(
                    f"[agents/controller.py] 📬 发现排队的意向 {x.intention_id}，状态还是 {x.status}，准备弹出。"
                )
                return x
        print("[agents/controller.py] 🧘 队列里的意向都处理过了，静悄悄的。")
        return None
