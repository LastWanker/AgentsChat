from __future__ import annotations

import operator
from typing import TypedDict
from typing_extensions import Annotated


class WorldState(TypedDict, total=False):
    session_id: str
    tick: int
    # V2 world orchestration fields:
    # - world_running/stop_requested: explicit lifecycle control for service mode.
    # - world_tick/max_world_ticks_per_run: safe loop bound per invoke/stream call.
    # - world_commands: control-plane commands (create agent, inject task, stop world, ...).
    # - pending_* queues: extension points for orchestration side channels.
    world_running: bool
    stop_requested: bool
    stop_reason: str | None
    world_tick: int
    max_world_ticks_per_run: int
    loop_continue: bool
    world_commands: list[dict]
    applied_world_commands: list[dict]
    agent_status_map: dict[str, dict]
    pending_direct_chats: list[dict]
    pending_injections: list[dict]
    pending_mentions: list[dict]
    reply_wait_window_ms: int
    incoming_events: list[dict]
    pending_events: list[dict]
    routed_events: list[dict]
    routed_events_by_agent: dict[str, list[dict]]
    agents: list[str]
    runnable_agents: list[str]
    agent_tasks: list[dict]
    agent_task: dict
    agent_outputs: Annotated[list[dict], operator.add]
    world_outputs: list[dict]
    latest_events: list[dict]
    committed_event_ids: Annotated[list[str], operator.add]
    published_events: list[dict]
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
    enable_internal_loop: bool
    task_done: bool
    phase_override: str | None
    # V2 主字段：多动作计划（actions[]）。
    planned_actions: list[dict]
    plan_steps: list[dict]
    executed_step_ids: list[str]
    ready_steps: list[dict]
    step_results: list[dict]
    skill_context: dict
    selected_actions: list[dict]
    action_results: list[dict]
    plan_execution_report: dict
    guardrail_report: dict
    board_snapshot_digest: dict
    # V1 兼容字段：过渡期保留，后续移除。
    planned_action: str
    action_payload: dict
    citation_policy: str
    needs_retrieval: bool
    retrieval_channel: str
    retrieval_channels: list[str]
    enabled_retrieval_channels: list[str]
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
