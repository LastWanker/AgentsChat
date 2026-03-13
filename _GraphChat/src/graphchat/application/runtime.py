from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from langgraph.types import Command

from graphchat.application.graphs.agent_graph import build_agent_graph
from graphchat.application.graphs.subgraphs.board_subgraph import BoardDeps
from graphchat.application.graphs.subgraphs.retrieval_subgraph import RetrievalDeps
from graphchat.application.graphs.world_graph import build_world_graph
from graphchat.application.nodes.agent_nodes import AgentNodeDeps
from graphchat.application.nodes.world_nodes import WorldNodeDeps
from graphchat.application.skills.guard_profiles import (
    SkillGuardProfile,
    apply_profile_overrides,
    build_default_skill_profiles,
    default_profile_for_action,
)
from graphchat.domain.models.action_contract import default_action_registry
from graphchat.domain.models.event import Event
from graphchat.domain.models.schemas import validate_world_command_payload
from graphchat.infrastructure.llm.model_provider import build_model_provider
from graphchat.infrastructure.persistence.agent_registry import AgentRegistry
from graphchat.infrastructure.persistence.approval_queue import ApprovalQueueStore
from graphchat.infrastructure.persistence.board_store import BoardStore
from graphchat.infrastructure.persistence.checkpoint_store import (
    CheckpointBackend,
    build_runtime_checkpointers,
)
from graphchat.infrastructure.persistence.event_store import JsonlEventStore
from graphchat.infrastructure.persistence.scope_registry import DmRegistry, GroupRegistry
from graphchat.infrastructure.retrieval.providers import (
    LocalFileSearchProvider,
    PeerEventSearchProvider,
    WebSearchProvider,
)
from graphchat.infrastructure.retrieval.tag_index import TagInvertedIndex
from graphchat.infrastructure.retrieval.vector_index import VectorIndex


class GraphChatRuntime:
    def __init__(
        self,
        base_dir: str | Path,
        agents: list[str] | None = None,
        *,
        checkpointer_backend: CheckpointBackend = "auto",
        model_provider: Any | None = None,
        max_silent_rounds: int = 1,
        ttl_initial: int = 15,
        lastlife_threshold: int = 3,
        speak_reply_window_seconds: int = 10,
        reply_wait_window_ms: int = 10_000,
        max_world_ticks_per_run: int = 1,
        skill_guard_overrides: dict[str, dict] | None = None,
        test_mode: bool = False,
        enable_internal_loop: bool = False,
    ):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._default_agents = agents or ["agent_1", "agent_2", "agent_3"]
        self.max_silent_rounds = int(max_silent_rounds)
        # V2 参数：先按需求固定默认值，后续可配置化。
        self.ttl_initial = int(ttl_initial)
        self.lastlife_threshold = int(lastlife_threshold)
        self.speak_reply_window_seconds = 1 if test_mode else int(speak_reply_window_seconds)
        self.reply_wait_window_ms = 1_000 if test_mode else int(reply_wait_window_ms)
        self.max_world_ticks_per_run = max(1, int(max_world_ticks_per_run))
        self.enable_internal_loop = bool(enable_internal_loop)

        self.event_store = JsonlEventStore(self.base_dir / "sessions")
        self.board_store = BoardStore(self.base_dir / "sessions")
        self.agent_registry = AgentRegistry(
            self.base_dir / "registries" / "agent_registry.json",
            bootstrap_agents=self._default_agents,
        )
        for agent_id in self._default_agents:
            self.agent_registry.upsert_agent(agent_id=agent_id, enabled=True)
        self.group_registry = GroupRegistry(
            self.base_dir / "registries" / "group_registry.json",
            bootstrap_agents=self._default_agents,
        )
        self.dm_registry = DmRegistry(self.base_dir / "registries" / "dm_registry.json")
        self.approval_queue = ApprovalQueueStore(self.base_dir / "registries" / "approval_queue.json")
        self.tag_index = TagInvertedIndex()
        self.vector_index = VectorIndex()
        self.action_registry = default_action_registry()
        self.skill_profiles = apply_profile_overrides(
            build_default_skill_profiles(self.action_registry),
            skill_guard_overrides,
        )
        self.model_provider = model_provider or build_model_provider(
            allowed_actions=set(self.action_registry.keys()) | {"rag"},
        )
        self._agent_retrieval_channels: dict[str, list[str]] = {}
        self.idempotency_cache: set[str] = set()
        self._last_agent_status: dict[str, dict] = {}

        world_cp_handle, agent_cp_handle = build_runtime_checkpointers(
            base_dir=self.base_dir,
            backend=checkpointer_backend,
        )
        self.world_checkpointer = world_cp_handle.saver
        self.agent_checkpointer = agent_cp_handle.saver
        self._checkpoint_closers = [world_cp_handle.close, agent_cp_handle.close]
        self.checkpointer_meta = {
            "world": {"backend": world_cp_handle.backend, "location": world_cp_handle.location},
            "agent": {"backend": agent_cp_handle.backend, "location": agent_cp_handle.location},
        }

        agent_deps = AgentNodeDeps(
            action_registry=self.action_registry,
            model_provider=self.model_provider,
            idempotency_cache=self.idempotency_cache,
        )
        retrieval_deps = RetrievalDeps(
            tag_index=self.tag_index,
            vector_index=self.vector_index,
            enabled_channels={"world_history", "ask_peer", "file_search", "web_search"},
            peer_search_provider=PeerEventSearchProvider(self.event_store),
            web_search_provider=WebSearchProvider(),
            file_search_provider=LocalFileSearchProvider(self.base_dir / "sessions"),
        )
        board_deps = BoardDeps(board_store=self.board_store)

        self.agent_graph = build_agent_graph(
            deps=agent_deps,
            retrieval_deps=retrieval_deps,
            board_deps=board_deps,
            skill_profiles=self.skill_profiles,
            checkpointer=self.agent_checkpointer,
        )
        world_deps = WorldNodeDeps(
            event_store=self.event_store,
            run_agent=self._run_agent_once,
            group_registry=self.group_registry,
            dm_registry=self.dm_registry,
            agent_registry=self.agent_registry,
            register_agent=self.register_agent,
            set_agent_enabled=self.set_agent_enabled,
            set_agent_retrieval_channels=self.set_agent_retrieval_channels,
            list_agent_status=self._list_agent_status_map,
            direct_chat=self._direct_chat_once,
        )
        self.world_graph = build_world_graph(deps=world_deps, checkpointer=self.world_checkpointer)

    @property
    def agents(self) -> list[str]:
        return self.agent_registry.enabled_agent_ids()

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _record_agent_status(self, *, agent_id: str, status: str, session_id: str, detail: dict | None = None) -> None:
        self._last_agent_status[agent_id] = {
            "agent_id": agent_id,
            "status": status,
            "session_id": session_id,
            "updated_at": self._utc_now(),
            "detail": detail or {},
        }

    def _list_agent_status_map(self, session_id: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for agent_id in self.agents:
            status = dict(self._last_agent_status.get(agent_id, {}))
            if not status:
                status = {
                    "agent_id": agent_id,
                    "status": "idle",
                    "session_id": session_id,
                    "updated_at": self._utc_now(),
                    "detail": {},
                }
            out[agent_id] = status
        return out

    def _extract_interrupt_payload(self, result: dict) -> dict:
        interrupts = list(result.get("__interrupt__", []))
        if not interrupts:
            return {}
        first = interrupts[0]
        if isinstance(first, dict):
            return dict(first.get("value", first))
        value = getattr(first, "value", None)
        if isinstance(value, dict):
            return value
        return {"raw_interrupt": str(first)}

    def _index_emitted_events(self, events: list[dict]) -> None:
        for event in events:
            text = str(event.get("payload", {}).get("text", ""))
            event_id = event.get("event_id")
            if event_id:
                self.tag_index.add(text, event_id)
                self.vector_index.add(text, event_id)

    def _world_input(
        self,
        *,
        session_id: str,
        incoming_events: list[dict],
        world_commands: list[dict] | None = None,
        world_running: bool = False,
        max_world_ticks_per_run: int | None = None,
    ) -> dict:
        return {
            "session_id": session_id,
            "tick": 0,
            "world_running": bool(world_running),
            "stop_requested": False,
            "stop_reason": None,
            "world_tick": 0,
            "max_world_ticks_per_run": int(max_world_ticks_per_run or self.max_world_ticks_per_run),
            "loop_continue": False,
            "world_commands": list(world_commands or []),
            "applied_world_commands": [],
            "agent_status_map": {},
            "pending_direct_chats": [],
            "pending_injections": [],
            "pending_mentions": [],
            "reply_wait_window_ms": self.reply_wait_window_ms,
            "incoming_events": incoming_events,
            "pending_events": [],
            "agents": self.agents,
            "agent_outputs": [],
            "world_outputs": [],
            "latest_events": [],
            "published_events": [],
            "errors": [],
        }

    def _run_agent_once(self, session_id: str, task: dict) -> list[dict]:
        agent_id = task.get("agent_id", "agent_unknown")
        thread_id = f"{session_id}:agent:{agent_id}"
        state = {
            "session_id": session_id,
            "agent_id": agent_id,
            "visible_events": task.get("visible_events", []),
            # V2 主字段（当前先写入状态，不改变主流程决策）。
            "ttl_initial": self.ttl_initial,
            "global_ttl": self.ttl_initial,
            "lastlife_threshold": self.lastlife_threshold,
            "ttl_renewed": False,
            "agent_status": "idle",
            "speak_reply_window_seconds": self.speak_reply_window_seconds,
            "phase_override": task.get("phase_override"),
            "wake_mention": False,
            "should_wake": False,
            "task_done": False,
            "planned_actions": [],
            "plan_steps": [],
            "executed_step_ids": [],
            "ready_steps": [],
            "step_results": [],
            "skill_context": {},
            "selected_actions": [],
            "action_results": [],
            "plan_execution_report": {},
            "guardrail_report": {},
            "board_snapshot_digest": {},
            "planned_action": "listen_only",
            "action_payload": {},
            "citation_policy": "none",
            "needs_retrieval": False,
            "retrieval_channel": "world_history",
            "retrieval_channels": [],
            "candidates": [],
            "focus_reference": None,
            "support_references": [],
            "reroute_hint": None,
            "retrieval_trace": {},
            "board_snapshot": [],
            "board_operation": None,
            "approval_required": False,
            "approval_decision": None,
            "idempotency_key": "",
            "enable_internal_loop": self.enable_internal_loop,
            "enabled_retrieval_channels": list(
                self._agent_retrieval_channels.get(
                    agent_id,
                    ["world_history", "ask_peer", "file_search", "web_search"],
                )
            ),
            "silent_rounds": 0,
            "max_silent_rounds": self.max_silent_rounds,
            "emitted_events": [],
            "errors": [],
            "trace": {},
        }
        result = self.agent_graph.invoke(
            state,
            config={"configurable": {"thread_id": thread_id}},
        )

        if "__interrupt__" in result:
            interrupt_payload = self._extract_interrupt_payload(result)
            self.approval_queue.enqueue(
                session_id=session_id,
                agent_id=agent_id,
                thread_id=thread_id,
                interrupt_payload=interrupt_payload,
            )
            self._record_agent_status(
                agent_id=agent_id,
                status="awaiting_approval",
                session_id=session_id,
                detail={"interrupt": interrupt_payload},
            )
            return []

        emitted = list(result.get("emitted_events", []))
        self._index_emitted_events(emitted)
        self._record_agent_status(
            agent_id=agent_id,
            status="completed",
            session_id=session_id,
            detail={"emitted_count": len(emitted)},
        )
        return emitted

    def _direct_chat_once(self, request: dict) -> dict | None:
        agent_id = str(request.get("agent_id", "")).strip()
        if not agent_id:
            return None
        if agent_id not in self.agents:
            return None

        session_id = str(request.get("session_id") or request.get("source_session_id") or "")
        if not session_id:
            session_id = str(request.get("session_id", ""))
        if not session_id:
            return None

        scope = str(request.get("scope", "group:main"))
        actor_id = str(request.get("actor_id", "world"))
        text = str(request.get("text", "")).strip()
        mode = str(request.get("mode", "direct_chat"))

        history = self.event_store.list_events(session_id)[-6:]
        context = [
            f"{item.get('actor_id', '?')}: {str(item.get('payload', {}).get('text', ''))[:120]}"
            for item in history
            if isinstance(item, dict)
        ]
        reply_text = ""
        direct_reply_fn = getattr(self.model_provider, "direct_reply", None)
        if callable(direct_reply_fn):
            try:
                result = direct_reply_fn(
                    {
                        "agent_id": agent_id,
                        "mode": mode,
                        "scope": scope,
                        "actor_id": actor_id,
                        "text": text,
                        "context": context,
                    }
                )
                if isinstance(result, dict):
                    reply_text = str(result.get("text", "")).strip()
                elif isinstance(result, str):
                    reply_text = result.strip()
            except Exception:
                reply_text = ""
        if not reply_text:
            reply_text = f"[direct_reply:{agent_id}] {text}" if text else f"[direct_reply:{agent_id}] received"

        event = Event(
            session_id=session_id,
            world_scope=scope,
            actor_id=agent_id,
            action_id="direct_reply",
            action_version="1.0.0",
            payload={
                "text": reply_text,
                "mode": mode,
                "to_actor": actor_id,
                "request_id": str(request.get("request_id", "")),
                "source_event_id": request.get("source_event_id"),
            },
            trace={"node": "direct_chat", "mode": mode},
        ).to_dict()
        self._record_agent_status(
            agent_id=agent_id,
            status="responded_direct",
            session_id=session_id,
            detail={"mode": mode},
        )
        return event

    def submit_user_text(
        self,
        session_id: str,
        text: str,
        world_scope: str = "group:main",
        actor_id: str = "user",
    ) -> list[dict]:
        incoming_event = Event(
            session_id=session_id,
            world_scope=world_scope,
            actor_id=actor_id,
            action_id="speak",
            action_version="1.0.0",
            payload={"text": text},
            trace={"node": "input_adapter"},
        ).to_dict()

        result = self.world_graph.invoke(
            self._world_input(
                session_id=session_id,
                incoming_events=[incoming_event],
                world_commands=[],
                world_running=False,
                max_world_ticks_per_run=1,
            ),
            config={"configurable": {"thread_id": f"{session_id}:world"}},
        )
        return list(result.get("published_events", []))

    def _normalize_world_command(self, *, session_id: str, command: dict, created_by: str = "api") -> dict:
        row = dict(command)
        row.setdefault("command_id", f"wc_{uuid4().hex[:12]}")
        row.setdefault("session_id", session_id)
        row.setdefault("scope", "group:main")
        row.setdefault("payload", {})
        row.setdefault("priority", 50)
        row.setdefault("created_by", created_by)
        row.setdefault("created_at", self._utc_now())
        parsed, err = validate_world_command_payload(row)
        if err:
            raise ValueError(f"invalid world command: {err}")
        if parsed is None:
            raise ValueError("invalid world command: unknown parse error")
        return parsed

    def submit_world_commands(
        self,
        *,
        session_id: str,
        commands: list[dict],
        created_by: str = "api",
        world_running: bool = False,
        max_world_ticks_per_run: int | None = None,
    ) -> dict:
        rows = [
            self._normalize_world_command(session_id=session_id, command=item, created_by=created_by)
            for item in commands
        ]
        result = self.world_graph.invoke(
            self._world_input(
                session_id=session_id,
                incoming_events=[],
                world_commands=rows,
                world_running=world_running,
                max_world_ticks_per_run=max_world_ticks_per_run,
            ),
            config={"configurable": {"thread_id": f"{session_id}:world"}},
        )
        return {
            "published_events": list(result.get("published_events", [])),
            "applied_world_commands": list(result.get("applied_world_commands", [])),
            "errors": list(result.get("errors", [])),
        }

    def submit_world_command(
        self,
        *,
        session_id: str,
        command: dict,
        created_by: str = "api",
        world_running: bool = False,
        max_world_ticks_per_run: int | None = None,
    ) -> dict:
        return self.submit_world_commands(
            session_id=session_id,
            commands=[command],
            created_by=created_by,
            world_running=world_running,
            max_world_ticks_per_run=max_world_ticks_per_run,
        )

    def direct_chat_with_agent(
        self,
        *,
        session_id: str,
        agent_id: str,
        text: str,
        scope: str = "group:main",
        actor_id: str = "user",
    ) -> dict | None:
        event = self._direct_chat_once(
            {
                "session_id": session_id,
                "request_id": f"dc_{uuid4().hex[:12]}",
                "agent_id": agent_id,
                "text": text,
                "scope": scope,
                "actor_id": actor_id,
                "mode": "direct_chat",
            }
        )
        if event is None:
            return None
        self.event_store.append_events(session_id, [event])
        self._index_emitted_events([event])
        return event

    def force_phase(
        self,
        *,
        session_id: str,
        agent_id: str,
        phase: str = "force_plan",
        reason: str = "",
        created_by: str = "boss",
    ) -> dict:
        return self.submit_world_command(
            session_id=session_id,
            command={
                "type": "force_phase",
                "scope": "group:main",
                "payload": {"agent_id": agent_id, "phase": phase, "reason": reason},
            },
            created_by=created_by,
            world_running=False,
            max_world_ticks_per_run=1,
        )

    def start_world_loop(
        self,
        *,
        session_id: str,
        commands: list[dict] | None = None,
        created_by: str = "boss",
        max_world_ticks_per_run: int = 3,
    ) -> dict:
        return self.submit_world_commands(
            session_id=session_id,
            commands=list(commands or []),
            created_by=created_by,
            world_running=True,
            max_world_ticks_per_run=max_world_ticks_per_run,
        )

    def stop_world_loop(
        self,
        *,
        session_id: str,
        reason: str = "manual_stop",
        created_by: str = "boss",
    ) -> dict:
        return self.submit_world_command(
            session_id=session_id,
            command={
                "type": "stop_world",
                "scope": "group:main",
                "payload": {"reason": reason},
            },
            created_by=created_by,
            world_running=False,
            max_world_ticks_per_run=1,
        )

    def stream_user_text(
        self,
        *,
        session_id: str,
        text: str,
        world_scope: str = "group:main",
        actor_id: str = "user",
    ) -> Iterator[dict]:
        incoming_event = Event(
            session_id=session_id,
            world_scope=world_scope,
            actor_id=actor_id,
            action_id="speak",
            action_version="1.0.0",
            payload={"text": text},
            trace={"node": "input_adapter"},
        ).to_dict()
        config = {"configurable": {"thread_id": f"{session_id}:world"}}
        initial_state = self._world_input(
            session_id=session_id,
            incoming_events=[incoming_event],
            world_commands=[],
            world_running=False,
            max_world_ticks_per_run=1,
        )
        for chunk in self.world_graph.stream(initial_state, config=config, stream_mode="updates"):
            yield {"type": "node_update", "session_id": session_id, "data": chunk}
            if not isinstance(chunk, dict):
                continue
            for update in chunk.values():
                if not isinstance(update, dict):
                    continue
                published = update.get("published_events")
                if isinstance(published, list):
                    for event in published:
                        yield {"type": "message", "session_id": session_id, "data": event}
        pending = self.list_approval_requests(session_id=session_id, status="pending")
        if pending:
            yield {"type": "approval_pending", "session_id": session_id, "data": pending}

    def list_approval_requests(
        self,
        *,
        session_id: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        return self.approval_queue.list_requests(session_id=session_id, status=status)

    def resolve_approval(
        self,
        *,
        request_id: str,
        decision: str,
        reviewer: str = "api",
        note: str | None = None,
    ) -> dict:
        request = self.approval_queue.get_request(request_id)
        if request is None:
            raise ValueError(f"approval request not found: {request_id}")
        if str(request.get("status")) != "pending":
            return {"request": request, "resumed_events": []}

        resolved = self.approval_queue.resolve(
            request_id=request_id,
            decision=decision,
            reviewer=reviewer,
            note=note,
        )
        thread_id = str(request.get("thread_id"))
        resumed = self.agent_graph.invoke(
            Command(resume={"decision": decision, "note": note}),
            config={"configurable": {"thread_id": thread_id}},
        )
        resumed_events = list(resumed.get("emitted_events", []))
        session_id = str(request.get("session_id"))
        if resumed_events:
            self.event_store.append_events(session_id, resumed_events)
            self._index_emitted_events(resumed_events)
        self._record_agent_status(
            agent_id=str(request.get("agent_id", "")),
            status="resumed",
            session_id=session_id,
            detail={"decision": decision, "emitted_count": len(resumed_events)},
        )
        return {"request": resolved or request, "resumed_events": resumed_events}

    def register_agent(
        self,
        *,
        agent_id: str,
        enabled: bool = True,
        role: str = "member",
        permissions: list[str] | None = None,
        join_main_group: bool = True,
    ) -> dict:
        record = self.agent_registry.upsert_agent(
            agent_id=agent_id,
            enabled=enabled,
            role=role,
            permissions=permissions,
        )
        if join_main_group:
            self.group_registry.add_member("main", agent_id)
        return record

    def set_agent_enabled(self, agent_id: str, enabled: bool) -> dict | None:
        return self.agent_registry.set_enabled(agent_id, enabled)

    def set_group_members(self, group_id: str, members: list[str]) -> None:
        self.group_registry.set_members(group_id, members)

    def set_agent_retrieval_channels(self, agent_id: str, channels: list[str]) -> None:
        allowed = {"world_history", "ask_peer", "file_search", "web_search"}
        normalized = [str(item).strip() for item in channels if str(item).strip() in allowed]
        if not normalized:
            normalized = ["world_history"]
        self._agent_retrieval_channels[agent_id] = normalized

    def set_skill_guard_profile(self, action_id: str, **patch) -> SkillGuardProfile:
        base = self.skill_profiles.get(action_id) or default_profile_for_action(
            action_id, self.action_registry.get(action_id)
        )
        fields = {key: value for key, value in patch.items() if hasattr(base, key)}
        updated = replace(base, **fields)
        self.skill_profiles[action_id] = updated
        return updated

    def allow_dm(self, a: str, b: str) -> None:
        self.dm_registry.register_pair(a, b)

    def revoke_dm(self, a: str, b: str) -> None:
        self.dm_registry.revoke_pair(a, b)

    def get_observability_snapshot(self, session_id: str | None = None) -> dict:
        pending = self.list_approval_requests(session_id=session_id, status="pending")
        out = {
            "checkpointers": self.checkpointer_meta,
            "agents": self.agent_registry.list_agents(include_disabled=True),
            "last_agent_status": self._last_agent_status,
            "agent_retrieval_channels": self._agent_retrieval_channels,
            "skill_guard_profiles": {
                action_id: profile.__dict__ for action_id, profile in self.skill_profiles.items()
            },
            "pending_approvals": pending,
            "pending_approval_count": len(pending),
        }
        if session_id:
            out["session_event_count"] = len(self.event_store.list_events(session_id))
        return out

    def close(self) -> None:
        for closer in self._checkpoint_closers:
            try:
                closer()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
