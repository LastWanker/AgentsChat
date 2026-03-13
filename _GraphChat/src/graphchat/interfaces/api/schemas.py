from __future__ import annotations

from pydantic import BaseModel, Field


class MessageRequest(BaseModel):
    text: str = Field(min_length=1)
    world_scope: str = "group:main"
    actor_id: str = "user"


class WorldCommandsRequest(BaseModel):
    command: dict | None = None
    commands: list[dict] = Field(default_factory=list)
    created_by: str = "api"
    world_running: bool = False
    max_world_ticks_per_run: int | None = None


class ResolveApprovalRequest(BaseModel):
    decision: str = Field(min_length=1)
    reviewer: str = "api"
    note: str | None = None


class DirectChatRequest(BaseModel):
    agent_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    scope: str = "group:main"
    actor_id: str = "user"

