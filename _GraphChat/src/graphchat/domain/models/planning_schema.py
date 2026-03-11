from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


SCOPE_RE = re.compile(r"^(group:main|group:[A-Za-z0-9_\-]+|dm:[A-Za-z0-9_\-]+:[A-Za-z0-9_\-]+)$")
MAX_ACTION_STEPS = 6

# V2 默认动作优先级（值越小优先级越高）。LLM 若给出 step_index，会覆盖该默认排序。
DEFAULT_ACTION_PRIORITY: dict[str, int] = {
    "maintain_board": 10,
    "board_item_upserted": 10,
    "board_item_deleted": 10,
    "board_item_archived": 10,
    "board_item_priority_set": 10,
    "board_item_due_set": 10,
    "board_gc_performed": 10,
    "speak": 20,
    "vote_decision": 30,
    "dissolve_group": 30,
    "escalate_to_boss": 30,
}


class ActionIntent(BaseModel):
    action_id: str = Field(min_length=1)
    plan_text: str = Field(default="")
    payload: dict[str, Any] = Field(default_factory=dict)
    target_scope: str = Field(default="group:main")
    target_agents: list[str] = Field(default_factory=list)
    priority: int = Field(default=100, ge=1, le=999)
    can_skip: bool = False
    step_index: int | None = Field(default=None, ge=1, le=MAX_ACTION_STEPS)

    @field_validator("target_scope")
    @classmethod
    def validate_target_scope(cls, v: str) -> str:
        if not SCOPE_RE.match(str(v)):
            raise ValueError(f"invalid target_scope: {v}")
        return str(v)

    @field_validator("target_agents")
    @classmethod
    def normalize_target_agents(cls, v: list[str]) -> list[str]:
        out = [str(item).strip() for item in v if str(item).strip()]
        return out


class ActionPlanOutput(BaseModel):
    reasoning_summary: str = ""
    task_done: bool = False
    actions: list[ActionIntent] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_action_limit(self):
        if len(self.actions) > MAX_ACTION_STEPS:
            raise ValueError(f"actions exceeds limit {MAX_ACTION_STEPS}")
        return self


def normalize_actions_v2(
    *,
    actions: list[dict[str, Any]],
    allowed_actions: set[str] | None = None,
) -> list[dict[str, Any]]:
    allowed = set(allowed_actions or [])
    parsed: list[ActionIntent] = []
    for item in actions:
        try:
            parsed_item = ActionIntent.model_validate(item)
        except ValidationError:
            continue
        if allowed and parsed_item.action_id not in allowed:
            continue
        if parsed_item.priority == 100:
            parsed_item.priority = DEFAULT_ACTION_PRIORITY.get(parsed_item.action_id, 100)
        parsed.append(parsed_item)
    parsed.sort(
        key=lambda x: (
            0 if x.step_index is not None else 1,
            x.step_index if x.step_index is not None else 999,
            x.priority,
        )
    )
    return [item.model_dump() for item in parsed[:MAX_ACTION_STEPS]]

