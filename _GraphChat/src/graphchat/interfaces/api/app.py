from __future__ import annotations

from typing import Iterator

from graphchat.application.runtime import GraphChatRuntime


class GraphChatAPI:
    def __init__(self, runtime: GraphChatRuntime):
        self.runtime = runtime

    def post_message(self, session_id: str, text: str) -> list[dict]:
        # 待拓展：可替换为 FastAPI/Flask 路由层。
        return self.runtime.submit_user_text(session_id=session_id, text=text)

    def stream_message(self, session_id: str, text: str) -> Iterator[dict]:
        return self.runtime.stream_user_text(session_id=session_id, text=text)

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

    def get_observability(self, session_id: str | None = None) -> dict:
        return self.runtime.get_observability_snapshot(session_id=session_id)
