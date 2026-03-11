from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from langgraph.types import Command

from graphchat.application.graphs.agent_graph import build_agent_graph
from graphchat.application.graphs.subgraphs.board_subgraph import BoardDeps
from graphchat.application.graphs.subgraphs.retrieval_subgraph import RetrievalDeps
from graphchat.application.graphs.world_graph import build_world_graph
from graphchat.application.nodes.agent_nodes import AgentNodeDeps
from graphchat.application.nodes.world_nodes import WorldNodeDeps
from graphchat.domain.models.action_contract import default_action_registry
from graphchat.domain.models.event import Event
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
        test_mode: bool = False,
    ):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._default_agents = agents or ["agent_1", "agent_2", "agent_3"]
        self.max_silent_rounds = int(max_silent_rounds)
        # V2 参数：先按需求固定默认值，后续可配置化。
        self.ttl_initial = int(ttl_initial)
        self.lastlife_threshold = int(lastlife_threshold)
        self.speak_reply_window_seconds = 1 if test_mode else int(speak_reply_window_seconds)

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
        self.model_provider = model_provider or build_model_provider(
            allowed_actions=self.action_registry.keys(),
        )
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
            checkpointer=self.agent_checkpointer,
        )
        world_deps = WorldNodeDeps(
            event_store=self.event_store,
            run_agent=self._run_agent_once,
            group_registry=self.group_registry,
            dm_registry=self.dm_registry,
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

    def _world_input(self, *, session_id: str, incoming_events: list[dict]) -> dict:
        return {
            "session_id": session_id,
            "tick": 0,
            "incoming_events": incoming_events,
            "pending_events": [],
            "agents": self.agents,
            "agent_outputs": [],
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
            "task_done": False,
            "planned_actions": [],
            "action_results": [],
            "silent_rounds": 0,
            "max_silent_rounds": self.max_silent_rounds,
            "emitted_events": [],
            "errors": [],
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
            self._world_input(session_id=session_id, incoming_events=[incoming_event]),
            config={"configurable": {"thread_id": f"{session_id}:world"}},
        )
        return list(result.get("published_events", []))

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
        initial_state = self._world_input(session_id=session_id, incoming_events=[incoming_event])
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
