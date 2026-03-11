from __future__ import annotations

import operator
from typing import TypedDict
from typing_extensions import Annotated


class WorldState(TypedDict, total=False):
    session_id: str
    tick: int
    incoming_events: list[dict]
    pending_events: list[dict]
    routed_events: list[dict]
    routed_events_by_agent: dict[str, list[dict]]
    agents: list[str]
    runnable_agents: list[str]
    agent_tasks: list[dict]
    agent_task: dict
    agent_outputs: Annotated[list[dict], operator.add]
    committed_event_ids: Annotated[list[str], operator.add]
    published_events: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]


class AgentState(TypedDict, total=False):
    session_id: str
    agent_id: str
    visible_events: list[dict]
    last_event: dict
    silent_rounds: int
    max_silent_rounds: int
    wake_mention: bool
    should_wake: bool
    agent_status: str
    global_ttl: int
    ttl_initial: int
    lastlife_threshold: int
    ttl_renewed: bool
    speak_reply_window_seconds: int
    task_done: bool
    phase_override: str | None
    # V2 主字段：多动作计划（actions[]）。
    planned_actions: list[dict]
    selected_actions: list[dict]
    action_results: list[dict]
    guardrail_report: dict
    board_snapshot_digest: dict
    # V1 兼容字段：过渡期保留，后续移除。
    planned_action: str
    action_payload: dict
    citation_policy: str
    needs_retrieval: bool
    retrieval_channel: str
    retrieval_channels: list[str]
    candidates: list[dict]
    focus_reference: str | None
    support_references: list[str]
    reroute_hint: str | None
    retrieval_trace: dict
    board_snapshot: list[dict]
    board_operation: dict | None
    approval_required: bool
    approval_decision: str | None
    idempotency_key: str
    emitted_events: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]
    trace: dict
