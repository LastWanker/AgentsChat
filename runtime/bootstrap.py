# runtime/bootstrap.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, TextIO
import atexit
import sys
from platform.world import World
from platform.observers import AgentObserver
from agents.controller import AgentController
from runtime.loop import RuntimeLoop
from runtime.scheduler import Scheduler
from runtime.scheduler_strategies import get_strategy
from platform.router import Router
from agents.interpreter import IntentInterpreter
from agents.agent import Agent
from events.id_generator import next_event_id
from events.store import EventStore
from events.types import Event, normalize_event_dict
from events.references import normalize_references
from events.intention_finalizer import IntentionFinalizer, FinalizerConfig
from events.query import EventQuery
from events.reference_resolver import ReferenceResolver
from agents.proposer import IntentionProposer, ProposerConfig
from events.session_memory import SessionMemory
from runtime.maintenance import SessionMaintenanceObserver


@dataclass
class RuntimeConfig:
    agents: List[Agent]
    policy_path: str

    enable_llm: bool = False
    llm_client: Optional[object] = None  # 先占位
    llm_mode: str = "async"
    allow_empty_policy: bool = False

    # Store/session
    data_dir: str = "data/sessions"
    session_id: Optional[str] = None  # 强制指定新 session 名称
    resume_session_id: Optional[str] = None  # 恢复已有 session
    session_metadata: Optional[Dict[str, Any]] = None

    # UI
    ui_enabled: bool = False
    ui_auto_open: bool = False
    ui_host: str = "127.0.0.1"
    ui_port: int = 8000


    # Loop
    max_ticks: int = 50
    seed_events: Optional[List[dict]] = None  # 允许 boss/测试注入事件
    scheduler_strategy: str = "recency"
    scheduler_strategy_config: Optional[Dict[str, Any]] = None


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
    ui_server: Any | None = None


class _TeeStream:
    def __init__(self, stream: TextIO, log_file: TextIO, log_path: Path):
        self._stream = stream
        self._log_file = log_file
        self._tee_log_path = log_path

    def write(self, message: str) -> int:
        self._log_file.write(message)
        return self._stream.write(message)

    def flush(self) -> None:
        self._log_file.flush()
        self._stream.flush()

    def isatty(self) -> bool:
        return getattr(self._stream, "isatty", lambda: False)()

    @property
    def encoding(self) -> str | None:
        return getattr(self._stream, "encoding", None)


def _enable_terminal_logging(session_dir: Path) -> None:
    log_path = session_dir / "terminal.log"
    log_file = log_path.open("a", encoding="utf-8")

    def _wrap(stream: TextIO) -> TextIO:
        if getattr(stream, "_tee_log_path", None) == log_path:
            return stream
        return _TeeStream(stream, log_file, log_path)

    sys.stdout = _wrap(sys.stdout)
    sys.stderr = _wrap(sys.stderr)
    atexit.register(log_file.close)
    print(f"[runtime/bootstrap.py] 🧾 终端日志将写入 {log_path}。")


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
            normalized = normalize_event_dict(seed)
            normalized_event_id = normalized.get("event_id") or next_event_id()
            ev = Event(
                event_id=normalized_event_id,
                type=normalized["type"],
                sender=normalized["sender"],
                sender_name=normalized.get("sender_name", ""),
                sender_role=normalized.get("sender_role", ""),
                content=normalized.get("content", {}),
                references=normalize_references(normalized.get("references", [])),
                tags=normalized.get("tags", []),
                metadata=normalized.get("metadata", {}),
                timestamp=normalized.get("timestamp", datetime.now(UTC).isoformat()),
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
    _enable_terminal_logging(store.session_dir)
    query = EventQuery(store)
    memory = SessionMemory(
        base_dir=store.session_dir,
        agents=cfg.agents,
        llm_client=cfg.llm_client,
        llm_mode=cfg.llm_mode,
    )
    print(
        f"[runtime/bootstrap.py] 🧱 正在搭建世界底座，初始化 EventStore 与 EventQuery，session={store.session_id}。"
    )
    ui_server = None
    if cfg.ui_enabled:
        from ui.live_ui import start_live_ui_server

        ui_server = start_live_ui_server(
            data_dir=store.base_dir,
            session_id=store.session_id,
            host=cfg.ui_host,
            port=cfg.ui_port,
            auto_open=cfg.ui_auto_open,
        )
    world = World(store=store) if "store" in World.__init__.__code__.co_varnames else World()
    print("[runtime/bootstrap.py] 🌍 World 构建完成，准备接线各路组件。")

    # === Proposer/Interpreter ===
    # proposer = IntentionProposer(enable_llm=cfg.enable_llm, llm_client=cfg.llm_client)
    # interpreter = IntentInterpreter(policy_path=cfg.policy_path)  # 你现在 Interpreter 读 yaml
    proposer = IntentionProposer(
        config=ProposerConfig(enable_llm=cfg.enable_llm, llm_mode=cfg.llm_mode),
        llm_client=cfg.llm_client,
    )
    interpreter = IntentInterpreter(
        constraint_path=cfg.policy_path,
        allow_empty_policy=cfg.allow_empty_policy,
    )  # 现在 Interpreter 读 yaml
    print("[runtime/bootstrap.py] 🧠 IntentionProposer 与 IntentInterpreter 已就绪。")

    # === Scheduler/Router/Controller/Loop ===
    scheduler_strategy = get_strategy(cfg.scheduler_strategy)
    scheduler = Scheduler(
        strategy=scheduler_strategy,
        strategy_config=cfg.scheduler_strategy_config,
    )
    router = Router(
        world=world,
        store=store,
        interpreter=interpreter,
    )
    controller = AgentController(
        agents=cfg.agents,
        proposer=proposer,
        store=store,
        query=query,
        memory=memory,
    )
    resolver = ReferenceResolver(query, tag_pool=memory.tag_pool)
    finalizer = IntentionFinalizer(
        resolver,
        config=FinalizerConfig(enable_llm=cfg.enable_llm, llm_mode=cfg.llm_mode),
        llm_client=cfg.llm_client,
        memory=memory,
    )
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
    world.add_observer(SessionMaintenanceObserver(memory=memory, store=store))
    print("[runtime/bootstrap.py] 🧹 SessionMaintenanceObserver 启用，负责事后维护。")

    # === 注入 seed events（Boss 或测试用）===
    if cfg.seed_events:
        first_seed: Event | None = None
        seed_senders: list[str] = []
        for e in cfg.seed_events:
            ev = _normalize_seed_event(e)
            store.append(ev)
            world.emit(ev)
            if first_seed is None:
                first_seed = ev
            if ev.sender is not None:
                seed_senders.append(str(ev.sender))
        store.sync_event_id_counter_from_store()
        if seed_senders:
            scheduler.mark_seed_speakers(seed_senders, loop_tick=0)
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
        ui_server=ui_server,
    )
