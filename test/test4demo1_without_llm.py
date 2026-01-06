"""最小可运行 demo：构造 World/Router/RuntimeLoop 并跑一轮意向。"""
from pathlib import Path

from agents.agent import Agent
from agents.controller import AgentController
from agents.interpreter import IntentInterpreter
from events.intention_finalizer import IntentionFinalizer
from events.reference_resolver import ReferenceResolver
from platform.observers import AgentObserver, ConsoleObserver
from platform.router import Router
from platform.world import World
from events.store import EventStore
from events.query import EventQuery
from runtime.loop import RuntimeLoop
from runtime.scheduler import Scheduler


# POLICY_PATH = "policies/intent_constraint.yaml"
# 获取项目根目录
ROOT_DIR = Path(__file__).parent.parent
POLICY_PATH = str(ROOT_DIR / "policies" / "intent_constraint.yaml")


def build_demo():
    print(f"[main.py] 🧩 正在组装 demo，文件在 {__file__}，请系好安全带～")

    world = World()
    print("[main.py] 🌍 世界 World 已经出生，准备接收各种事件。")

    store = EventStore()
    query = EventQuery(store)
    print("[main.py] 📚 事件仓库开门营业，所有动静都会记下来。")

    interpreter = IntentInterpreter(constraint_path=POLICY_PATH, allow_empty_policy=True)
    print(f"[main.py] 📜 解释器装载策略：{POLICY_PATH}，等着翻译意向。")

    agents = [
        Agent(name="Alice", role="Explorer", expertise=["demo"]),
        Agent(name="Bob", role="Responder", expertise=["demo"]),
    ]
    print(f"[main.py] 🤖 造好两个小伙伴：{[a.name for a in agents]}，他们各司其职。")

    controller = AgentController(agents, store=store, query=query)
    controller.seed_demo_intentions()
    print("[main.py] 📨 控制器已塞入第一批意向，感觉有人要开口说话了。")

    scheduler = Scheduler()
    print("[main.py] ⏰ 调度器就位，谁先说话由它安排。")
    router = Router(world=world, store=store, interpreter=interpreter)
    print("[main.py] 🛣️ 路由器搭好管道，准备把意向送去成事件。")

    # 观察者：控制台 + 每个 Agent 自己
    world.add_observer(ConsoleObserver())
    for ag in agents:
        world.add_observer(AgentObserver(ag))
    print("[main.py] 👀 观察者全体上线，所有风吹草动都会被看到。")

    resolver = ReferenceResolver(query)
    finalizer = IntentionFinalizer(resolver)
    loop = RuntimeLoop(controller, scheduler, router, finalizer=finalizer)
    print("[main.py] 🔄 循环引擎启动完毕，随时可以开跑。\n")
    return loop, world, store, agents


def main():
    loop, world, _, agents = build_demo()
    print("[main.py] 🚀 demo 要开跑啦，先预热一下。")
    loop.run(max_ticks=10)
    print("[main.py] 🏁 循环结束，来看看大家都经历了什么。")

    # 跑完后，打印每个 Agent 看到的 event_id，验证闭环
    for ag in agents:
        # print(f"Agent {ag.name} saw events: {ag.memory}")
        print(f"[main.py] 🧠 Agent {ag.name} 记住的事件列表：{ag.memory}")


if __name__ == "__main__":
    main()