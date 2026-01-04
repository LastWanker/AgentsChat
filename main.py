"""最小可运行 demo：构造 World/Router/RuntimeLoop 并跑一轮意向。"""
from agents.agent import Agent
from agents.controller import AgentController
from agents.interpreter import IntentInterpreter
from platform.observers import AgentObserver, ConsoleObserver
from platform.router import Router
from platform.world import World
from events.store import EventStore
from runtime.loop import RuntimeLoop
from runtime.scheduler import Scheduler


POLICY_PATH = "policies/intent_constraint.yaml"


def build_demo():
    world = World()
    store = EventStore()
    interpreter = IntentInterpreter(POLICY_PATH)

    agents = [
        Agent(name="Alice", role="Explorer", expertise=["demo"]),
        Agent(name="Bob", role="Responder", expertise=["demo"]),
    ]

    controller = AgentController(agents)
    controller.seed_demo_intentions()

    scheduler = Scheduler()
    router = Router(world, store, interpreter)

    # 观察者：控制台 + 每个 Agent 自己
    world.add_observer(ConsoleObserver())
    for ag in agents:
        world.add_observer(AgentObserver(ag))

    loop = RuntimeLoop(controller, scheduler, router)
    return loop, world, store, agents


def main():
    loop, world, _, agents = build_demo()
    loop.run(max_ticks=10)

    # 跑完后，打印每个 Agent 看到的 event_id，验证闭环
    for ag in agents:
        print(f"Agent {ag.name} saw events: {ag.memory}")


if __name__ == "__main__":
    main()