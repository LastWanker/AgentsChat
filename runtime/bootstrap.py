# runtime/bootstrap.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, List, Any

# 下面这些 import 按你的实际路径调整
from platform.world import World
from platform.observers import AgentObserver
from agents.controller import AgentController
from runtime.loop import RuntimeLoop
from runtime.scheduler import Scheduler
from platform.router import Router
from agents.interpreter import IntentInterpreter  # 如果你是 llm/interpreter.py 或别的位置就改
from agents.agent import Agent
from events.store import EventStore
from events.query import EventQuery
from agents.proposer import IntentionProposer  # 你现在的 proposer


@dataclass
class RuntimeConfig:
    agents: List[Agent]
    policy_path: str

    enable_llm: bool = False
    llm_client: Optional[object] = None   # 先占位

    # Router 纪律
    agent_cooldowns_sec: Optional[Dict[str, float]] = None

    # Loop
    max_ticks: int = 50
    seed_events: Optional[List[dict]] = None  # 允许 boss/测试注入事件


@dataclass
class AppRuntime:
    world: World
    store: EventStore
    query: EventQuery
    proposer: IntentionProposer
    interpreter: IntentInterpreter
    scheduler: Scheduler
    router: Router
    controller: AgentController
    loop: RuntimeLoop


def bootstrap(cfg: RuntimeConfig) -> AppRuntime:
    # === 底座 ===
    store = EventStore()
    query = EventQuery(store)
    world = World(store=store) if "store" in World.__init__.__code__.co_varnames else World()

    # === Proposer/Interpreter ===
    proposer = IntentionProposer(enable_llm=cfg.enable_llm, llm_client=cfg.llm_client)
    interpreter = IntentInterpreter(policy_path=cfg.policy_path)  # 你现在 Interpreter 读 yaml

    # === Scheduler/Router/Controller/Loop ===
    scheduler = Scheduler()
    router = Router(
        world=world,
        interpreter=interpreter,
        cooldowns_sec=cfg.agent_cooldowns_sec or {},
    )
    controller = AgentController(
        proposer=proposer,
        scheduler=scheduler,
    )
    loop = RuntimeLoop(
        world=world,
        scheduler=scheduler,
        router=router,
        max_ticks=cfg.max_ticks,
    )

    # === 插线：Agent 观察世界 ===
    for agent in cfg.agents:
        world.add_observer(AgentObserver(agent))
    # === 插线：Controller 观察世界（产出意向入队） ===
    world.add_observer(controller)

    # === 注入 seed events（Boss 或测试用）===
    if cfg.seed_events:
        for e in cfg.seed_events:
            world.emit(e)

    return AppRuntime(
        world=world,
        store=store,
        query=query,
        proposer=proposer,
        interpreter=interpreter,
        scheduler=scheduler,
        router=router,
        controller=controller,
        loop=loop,
    )
