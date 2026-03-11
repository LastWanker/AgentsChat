from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


WorldCommandType = Literal[
    "create_agent",
    "enable_agent",
    "disable_agent",
    "upsert_group",
    "upsert_dm_pair",
    "inject_task",
    "direct_chat",
    "force_phase",
    "stop_world",
]


class WorldCommand(BaseModel):
    command_id: str = Field(min_length=1)
    type: WorldCommandType
    session_id: str = Field(min_length=1)
    scope: str = Field(default="group:main", min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=50, ge=1, le=999)
    created_by: str = Field(default="system", min_length=1)
    created_at: str = Field(min_length=1)


def validate_world_command(command: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed = WorldCommand.model_validate(command)
    except ValidationError as e:
        return None, e.errors()[0]["msg"]
    return parsed.model_dump(), None

