from __future__ import annotations

from typing import Any, TypedDict


class WorkflowState(TypedDict, total=False):
    session_id: str
    tick: int
    current_agent_id: str | None
    trigger_event_id: str | None
    draft: dict[str, Any] | None
    final_intention: dict[str, Any] | None
    last_decision: dict[str, Any] | None
    halt_reason: str | None

