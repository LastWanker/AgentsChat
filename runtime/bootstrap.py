# runtime/bootstrap.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional, Dict, List, Any
from uuid import uuid4

from platform.world import World
from platform.observers import AgentObserver
from agents.controller import AgentController
from runtime.loop import RuntimeLoop
from runtime.scheduler import Scheduler
from platform.router import Router
from agents.interpreter import IntentInterpreter
from platform.request_tracker import RequestCompletionObserver
from agents.agent import Agent
from events.store import EventStore
from events.types import Event
from events.references import normalize_references
from events.intention_finalizer import IntentionFinalizer
from events.query import EventQuery
from events.reference_resolver import ReferenceResolver
from agents.proposer import IntentionProposer, ProposerConfig


@dataclass
class RuntimeConfig:
    agents: List[Agent]
    policy_path: str

    enable_llm: bool = False
    llm_client: Optional[object] = None  # 先占位
    allow_empty_policy: bool = False

    # Store/session
    data_dir: str = "data/sessions"
    session_id: Optional[str] = None  # 强制指定新 session 名称
    resume_session_id: Optional[str] = None  # 恢复已有 session
    session_metadata: Optional[Dict[str, Any]] = None

    # Router 纪律
    agent_cooldowns_sec: Optional[Dict[str, float]] = None
    inter_event_gap_sec: float = 0.0

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


def _normalize_seed_event(seed: Any) -> Event:
    """Ensure seed events are stored and broadcast consistently."""

    if isinstance(seed, Event):
        print(
            "[runtime/bootstrap.py] 🌱 Seed 已是 Event 对象，直接复用：",
            getattr(seed, "event_id", "<no-id>"),
        )
        return seed

    if isinstance(seed, dict):
        print(
            "[runtime/bootstrap.py] 🌱 收到 dict 类型 seed，准备规范化：",
            seed,
        )
        try:
            ev = Event(
                event_id=seed.get("event_id", str(uuid4())),
                type=seed["type"],
                timestamp=seed.get("timestamp", datetime.now(UTC).isoformat()),
                sender=seed["sender"],
                scope=seed.get("scope", "public"),
                content=seed.get("content", {}),
                references=normalize_references(seed.get("references", [])),
                recipients=seed.get("recipients", []),
                metadata=seed.get("metadata", {}),
                completed=seed.get("completed", True),
            )
            print(
                "[runtime/bootstrap.py] ✅ 规范化完成，生成 Event：",
                ev.event_id,
            )
            return ev
        except KeyError as exc:
            raise ValueError(f"Seed event dict 缺少必要字段：{exc}") from exc

    raise TypeError(f"不支持的种子事件类型：{type(seed)}")


def bootstrap(cfg: RuntimeConfig) -> AppRuntime:
    def _normalize_agent_cooldowns(
        cooldowns_sec: Optional[Dict[str, float]], agents: List[Agent]
    ) -> Dict[str, float]:
        if not cooldowns_sec:
            return {}

        name_to_id = {ag.name: ag.id for ag in agents}
        normalized: Dict[str, float] = {}
        for key, value in cooldowns_sec.items():
            agent_id = name_to_id.get(key, key)
            normalized[agent_id] = value
        return normalized

    # === 底座 ===
    session_meta = {
        "policy_path": cfg.policy_path,
        "enable_llm": cfg.enable_llm,
        "agents": [
            {"id": ag.id, "name": ag.name, "role": ag.role, "expertise": ag.expertise}
            for ag in cfg.agents
        ],
    }
    if cfg.session_metadata:
        session_meta.update(cfg.session_metadata)

    store = EventStore(
        base_dir=cfg.data_dir,
        session_id=cfg.resume_session_id or cfg.session_id,
        resume=cfg.resume_session_id is not None,
        metadata=session_meta,
    )
    query = EventQuery(store)
    print(
        f"[runtime/bootstrap.py] 🧱 正在搭建世界底座，初始化 EventStore 与 EventQuery，session={store.session_id}。"
    )
    world = World(store=store) if "store" in World.__init__.__code__.co_varnames else World()
    print("[runtime/bootstrap.py] 🌍 World 构建完成，准备接线各路组件。")

    # === Proposer/Interpreter ===
    # proposer = IntentionProposer(enable_llm=cfg.enable_llm, llm_client=cfg.llm_client)
    # interpreter = IntentInterpreter(policy_path=cfg.policy_path)  # 你现在 Interpreter 读 yaml
    proposer = IntentionProposer(
        config=ProposerConfig(enable_llm=cfg.enable_llm),
        llm_client=cfg.llm_client,
    )
    interpreter = IntentInterpreter(
        constraint_path=cfg.policy_path,
        allow_empty_policy=cfg.allow_empty_policy,
    )  # 现在 Interpreter 读 yaml
    print("[runtime/bootstrap.py] 🧠 IntentionProposer 与 IntentInterpreter 已就绪。")

    # === Scheduler/Router/Controller/Loop ===
    scheduler = Scheduler()
    cooldowns_sec = _normalize_agent_cooldowns(cfg.agent_cooldowns_sec, cfg.agents)
    router = Router(
        world=world,
        store=store,
        interpreter=interpreter,
        cooldowns_sec=cooldowns_sec,
        inter_event_gap_sec=cfg.inter_event_gap_sec,
    )
    controller = AgentController(
        agents=cfg.agents,
        proposer=proposer,
        store=store,
        query=query,
    )
    resolver = ReferenceResolver(query)
    finalizer = IntentionFinalizer(resolver)
    loop = RuntimeLoop(
        controller=controller,
        scheduler=scheduler,
        router=router,
        max_ticks=cfg.max_ticks,
        finalizer=finalizer,
    )
    print("[runtime/bootstrap.py] 🔌 Scheduler/Router/Controller/Loop 全部完成装配。")

    # === 插线：Agent 观察世界 ===
    for agent in cfg.agents:
        world.add_observer(AgentObserver(agent))
    print(f"[runtime/bootstrap.py] 👀 已为 {len(cfg.agents)} 个 Agent 接入世界观察通道。")
    # === 插线：Controller 观察世界（产出意向入队） ===
    world.add_observer(controller)
    print("[runtime/bootstrap.py] 🛰️ AgentController 也开始观察世界事件。")
    # === 插线：Request 完成监控（生成闭环声明） ===
    world.add_observer(
        RequestCompletionObserver(store=store, world=world, agents=cfg.agents)
    )
    print("[runtime/bootstrap.py] ✅ RequestCompletionObserver 启用，负责宣告请求完成。")

    # === 注入 seed events（Boss 或测试用）===
    if cfg.seed_events:
        for e in cfg.seed_events:
            ev = _normalize_seed_event(e)
            store.append(ev)
            world.emit(ev)
        print(f"[runtime/bootstrap.py] 🌱 预置种子事件 {len(cfg.seed_events)} 条已注入世界。")
    else:
        print("[runtime/bootstrap.py] 🌱 没有预置种子事件，等待运行时自然生成。")

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
