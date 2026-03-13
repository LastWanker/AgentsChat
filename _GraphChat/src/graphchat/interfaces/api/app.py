from __future__ import annotations

from typing import Iterator

from graphchat.application.runtime import GraphChatRuntime


class GraphChatAPI:
    def __init__(self, runtime: GraphChatRuntime):
        self.runtime = runtime

    def post_message(
        self,
        session_id: str,
        text: str,
        *,
        world_scope: str = "group:main",
        actor_id: str = "user",
    ) -> list[dict]:
        return self.runtime.submit_user_text(
            session_id=session_id,
            text=text,
            world_scope=world_scope,
            actor_id=actor_id,
        )

    def stream_message(
        self,
        session_id: str,
        text: str,
        *,
        world_scope: str = "group:main",
        actor_id: str = "user",
    ) -> Iterator[dict]:
        return self.runtime.stream_user_text(
            session_id=session_id,
            text=text,
            world_scope=world_scope,
            actor_id=actor_id,
        )

    def post_world_command(
        self,
        *,
        session_id: str,
        command: dict,
        created_by: str = "api",
        world_running: bool = False,
        max_world_ticks_per_run: int | None = None,
    ) -> dict:
        return self.runtime.submit_world_command(
            session_id=session_id,
            command=command,
            created_by=created_by,
            world_running=world_running,
            max_world_ticks_per_run=max_world_ticks_per_run,
        )

    def post_world_commands(
        self,
        *,
        session_id: str,
        commands: list[dict],
        created_by: str = "api",
        world_running: bool = False,
        max_world_ticks_per_run: int | None = None,
    ) -> dict:
        return self.runtime.submit_world_commands(
            session_id=session_id,
            commands=commands,
            created_by=created_by,
            world_running=world_running,
            max_world_ticks_per_run=max_world_ticks_per_run,
        )

    def list_approvals(self, session_id: str | None = None, status: str | None = "pending") -> list[dict]:
        return self.runtime.list_approval_requests(session_id=session_id, status=status)

    def resolve_approval(
        self,
        request_id: str,
        decision: str,
        reviewer: str = "api",
        note: str | None = None,
    ) -> dict:
        return self.runtime.resolve_approval(
            request_id=request_id,
            decision=decision,
            reviewer=reviewer,
            note=note,
        )

    def upsert_agent(
        self,
        *,
        agent_id: str,
        enabled: bool = True,
        role: str = "member",
        permissions: list[str] | None = None,
    ) -> dict:
        return self.runtime.register_agent(
            agent_id=agent_id,
            enabled=enabled,
            role=role,
            permissions=permissions,
        )

    def set_agent_enabled(self, agent_id: str, enabled: bool) -> dict | None:
        return self.runtime.set_agent_enabled(agent_id, enabled)

    def set_agent_retrieval_channels(self, agent_id: str, channels: list[str]) -> None:
        self.runtime.set_agent_retrieval_channels(agent_id, channels)

    def set_skill_guard_profile(self, action_id: str, **patch) -> dict:
        profile = self.runtime.set_skill_guard_profile(action_id, **patch)
        return dict(profile.__dict__)

    def list_agent_status(self, session_id: str) -> dict[str, dict]:
        snapshot = self.runtime.get_observability_snapshot(session_id=session_id)
        return dict(snapshot.get("last_agent_status", {}))

    def direct_chat(
        self,
        *,
        session_id: str,
        agent_id: str,
        text: str,
        scope: str = "group:main",
        actor_id: str = "user",
    ) -> dict | None:
        return self.runtime.direct_chat_with_agent(
            session_id=session_id,
            agent_id=agent_id,
            text=text,
            scope=scope,
            actor_id=actor_id,
        )

    def force_phase(
        self,
        *,
        session_id: str,
        agent_id: str,
        phase: str = "force_plan",
        reason: str = "",
        created_by: str = "boss",
    ) -> dict:
        return self.runtime.force_phase(
            session_id=session_id,
            agent_id=agent_id,
            phase=phase,
            reason=reason,
            created_by=created_by,
        )

    def start_world_loop(
        self,
        *,
        session_id: str,
        commands: list[dict] | None = None,
        created_by: str = "boss",
        max_world_ticks_per_run: int = 3,
    ) -> dict:
        return self.runtime.start_world_loop(
            session_id=session_id,
            commands=commands,
            created_by=created_by,
            max_world_ticks_per_run=max_world_ticks_per_run,
        )

    def stop_world_loop(
        self,
        *,
        session_id: str,
        reason: str = "manual_stop",
        created_by: str = "boss",
    ) -> dict:
        return self.runtime.stop_world_loop(
            session_id=session_id,
            reason=reason,
            created_by=created_by,
        )

    def get_observability(self, session_id: str | None = None) -> dict:
        return self.runtime.get_observability_snapshot(session_id=session_id)

    def list_session_events(self, session_id: str, *, limit: int = 100) -> list[dict]:
        rows = self.runtime.event_store.list_events(session_id)
        if limit <= 0:
            return rows
        return rows[-limit:]
