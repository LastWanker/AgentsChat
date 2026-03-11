from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents.agent import Agent

from ...application.controller import AgentController
from ...application.finalizer import FinalizerConfig, IntentionFinalizer, ReferenceResolver
from ...application.interpreter import IntentInterpreter
from ...application.memory import SessionMemory
from ...application.proposer import IntentionProposer, ProposerConfig
from ...application.router import IntentionRouter
from ...application.scheduler import Scheduler
from ...infrastructure.logging import enable_terminal_logging
from ...infrastructure.persistence import EventQuery, EventStore
from ...infrastructure.ui import start_live_ui_server
from ...interfaces.event_bus import WorldBus
from ...interfaces.observers import AgentObserver, SessionMaintenanceObserver
from ...workflow import LangGraphEngine, LegacyLoopEngine
from .config import RuntimeConfig
from .runtime import AppRuntime
from events.id_generator import next_event_id
from events.references import normalize_references
from events.types import Event, normalize_event_dict
from runtime.scheduler_strategies import get_strategy


def _normalize_seed_event(seed: Any) -> Event:
    if isinstance(seed, Event):
        return seed
    if isinstance(seed, dict):
        normalized = normalize_event_dict(seed)
        return Event(
            event_id=normalized.get("event_id") or next_event_id(),
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
    raise TypeError(f"unsupported seed event type: {type(seed)}")


def _build_session_meta(cfg: RuntimeConfig) -> dict[str, Any]:
    session_meta = {
        "policy_path": cfg.policy_path,
        "enable_llm": cfg.enable_llm,
        "agents": [
            {"id": ag.id, "name": ag.name, "role": ag.role, "expertise": ag.expertise}
            for ag in cfg.agents
        ],
        "workflow_engine": cfg.workflow_engine,
    }
    if cfg.session_metadata:
        session_meta.update(cfg.session_metadata)
    return session_meta


def _build_engine(
    cfg: RuntimeConfig,
    *,
    controller,
    scheduler,
    router,
    finalizer,
):
    if cfg.workflow_engine == "legacy":
        return LegacyLoopEngine(
            controller=controller,
            scheduler=scheduler,
            router=router,
            max_ticks=cfg.max_ticks,
            finalizer=finalizer,
        )
    if cfg.workflow_engine == "langgraph":
        if LangGraphEngine is None:
            print(
                "[app/bootstrap] langgraph not installed, fallback to legacy engine."
            )
            return LegacyLoopEngine(
                controller=controller,
                scheduler=scheduler,
                router=router,
                max_ticks=cfg.max_ticks,
                finalizer=finalizer,
            )
        try:
            return LangGraphEngine(
                controller=controller,
                scheduler=scheduler,
                router=router,
                max_ticks=cfg.max_ticks,
                finalizer=finalizer,
            )
        except Exception as exc:
            print(f"[app/bootstrap] langgraph engine init failed, fallback: {exc}")
            return LegacyLoopEngine(
                controller=controller,
                scheduler=scheduler,
                router=router,
                max_ticks=cfg.max_ticks,
                finalizer=finalizer,
            )
    raise ValueError(f"unknown workflow_engine={cfg.workflow_engine}")


def build_runtime(cfg: RuntimeConfig) -> AppRuntime:
    session_meta = _build_session_meta(cfg)
    store = EventStore(
        base_dir=cfg.data_dir,
        session_id=cfg.resume_session_id or cfg.session_id,
        resume=cfg.resume_session_id is not None,
        metadata=session_meta,
    )
    enable_terminal_logging(store.session_dir)
    query = EventQuery(store)
    memory = SessionMemory(
        base_dir=store.session_dir,
        agents=cfg.agents,
        llm_client=cfg.llm_client,
        llm_mode=cfg.llm_mode,
    )

    ui_server = None
    if cfg.ui_enabled:
        ui_server = start_live_ui_server(
            data_dir=Path(store.base_dir),
            session_id=store.session_id,
            host=cfg.ui_host,
            port=cfg.ui_port,
            auto_open=cfg.ui_auto_open,
        )

    world = WorldBus()
    proposer = IntentionProposer(
        config=ProposerConfig(enable_llm=cfg.enable_llm, llm_mode=cfg.llm_mode),
        llm_client=cfg.llm_client,
    )
    interpreter = IntentInterpreter(
        constraint_path=cfg.policy_path,
        allow_empty_policy=cfg.allow_empty_policy,
    )
    scheduler_strategy = get_strategy(cfg.scheduler_strategy)
    scheduler = Scheduler(
        strategy=scheduler_strategy,
        strategy_config=cfg.scheduler_strategy_config,
    )
    router = IntentionRouter(world=world, store=store, interpreter=interpreter)
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
    engine = _build_engine(
        cfg,
        controller=controller,
        scheduler=scheduler,
        router=router,
        finalizer=finalizer,
    )

    for agent in cfg.agents:
        world.add_observer(AgentObserver(agent))
    world.add_observer(controller)
    world.add_observer(SessionMaintenanceObserver(memory=memory, store=store))

    if cfg.seed_events:
        seed_senders: list[str] = []
        for seed in cfg.seed_events:
            ev = _normalize_seed_event(seed)
            store.append(ev)
            world.emit(ev)
            if ev.sender is not None:
                seed_senders.append(str(ev.sender))
        store.sync_event_id_counter_from_store()
        if seed_senders:
            scheduler.mark_seed_speakers(seed_senders, loop_tick=0)

    return AppRuntime(
        world=world,
        store=store,
        query=query,
        proposer=proposer,
        interpreter=interpreter,
        scheduler=scheduler,
        router=router,
        controller=controller,
        engine=engine,
        ui_server=ui_server,
    )


def build_default_agents() -> tuple[Agent, Agent, Agent]:
    boss = Agent("BOSS", role="boss", expertise=["authority"])
    alice = Agent("Alice", role="thinker", expertise=["logic"])
    bob = Agent("Bob", role="critic", expertise=["debate"])
    return boss, alice, bob
