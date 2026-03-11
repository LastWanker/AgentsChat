from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from graphchat.domain.models.planning_schema import (
    MAX_ACTION_STEPS,
    ActionPlanOutput,
    normalize_actions_v2,
)
from graphchat.domain.models.world_command import WorldCommand


_SCOPE_RE = re.compile(r"^(group:main|group:[A-Za-z0-9_\-]+|dm:[A-Za-z0-9_\-]+:[A-Za-z0-9_\-]+)$")
_BOARD_OPS = {"upsert", "delete", "archive", "set_priority", "set_due"}
_BOARD_PRIORITIES = {"low", "medium", "high", "urgent"}


class ReferenceSchema(BaseModel):
    event_id: str = Field(min_length=1)
    role: Literal["focus", "support", "context", "counter"] = "support"
    score: float | None = Field(default=None, ge=0.0, le=1.0)


class EventSchema(BaseModel):
    event_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    world_scope: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    action_version: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    references: list[ReferenceSchema] = Field(default_factory=list)
    focus_reference: str | None = None
    created_at: str = Field(min_length=1)
    trace: dict[str, Any] = Field(default_factory=dict)

    @field_validator("world_scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        if not _SCOPE_RE.match(v):
            raise ValueError(f"invalid world_scope: {v}")
        return v


class AgentPlanSchema(BaseModel):
    planned_action: str = Field(min_length=1)
    action_payload: dict[str, Any] = Field(default_factory=dict)
    citation_policy: Literal["none", "optional", "required_focus"] = "none"

    @field_validator("action_payload")
    @classmethod
    def validate_payload_scope(cls, payload: dict[str, Any]) -> dict[str, Any]:
        scope = payload.get("world_scope")
        if scope is not None and not _SCOPE_RE.match(str(scope)):
            raise ValueError(f"invalid payload.world_scope: {scope}")
        board_op = payload.get("board_op")
        if board_op is not None and str(board_op) not in _BOARD_OPS:
            raise ValueError(f"invalid payload.board_op: {board_op}")
        priority = payload.get("priority")
        if priority is not None and str(priority) not in _BOARD_PRIORITIES:
            raise ValueError(f"invalid payload.priority: {priority}")
        return payload


def validate_event(event: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed = EventSchema.model_validate(event)
    except ValidationError as e:
        return None, e.errors()[0]["msg"]
    return parsed.model_dump(), None


def validate_agent_plan(
    planned_action: Any,
    action_payload: Any,
    citation_policy: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed = AgentPlanSchema.model_validate(
            {
                "planned_action": planned_action,
                "action_payload": action_payload if isinstance(action_payload, dict) else {},
                "citation_policy": citation_policy or "none",
            }
        )
    except ValidationError as e:
        return None, e.errors()[0]["msg"]
    return parsed.model_dump(), None


def validate_action_plan_v2(
    *,
    reasoning_summary: Any,
    task_done: Any,
    actions: Any,
    allowed_actions: set[str] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed = ActionPlanOutput.model_validate(
            {
                "reasoning_summary": str(reasoning_summary or ""),
                "task_done": bool(task_done),
                "actions": actions if isinstance(actions, list) else [],
            }
        )
    except ValidationError as e:
        return None, e.errors()[0]["msg"]
    normalized = normalize_actions_v2(
        actions=[item.model_dump() for item in parsed.actions][:MAX_ACTION_STEPS],
        allowed_actions=allowed_actions,
    )
    return {
        "reasoning_summary": parsed.reasoning_summary,
        "task_done": parsed.task_done,
        "actions": normalized,
    }, None


def validate_world_command_payload(command: Any) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed = WorldCommand.model_validate(command if isinstance(command, dict) else {})
    except ValidationError as e:
        return None, e.errors()[0]["msg"]
    return parsed.model_dump(), None
