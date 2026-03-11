from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from langgraph.graph import START, END, StateGraph

from graphchat.application.state import AgentState
from graphchat.domain.models.board_item import BoardItem
from graphchat.infrastructure.persistence.board_store import BoardStore


@dataclass
class BoardDeps:
    board_store: BoardStore


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(v)


def build_board_subgraph(deps: BoardDeps):
    graph = StateGraph(AgentState)

    def board_read_node(state: AgentState) -> AgentState:
        snapshot = deps.board_store.list_items(
            state["session_id"],
            include_archived=True,
            include_deleted=False,
        )
        return {"board_snapshot": snapshot}

    def board_update_node(state: AgentState) -> AgentState:
        action = state.get("planned_action", "")
        if action not in {"maintain_board", "assign_task"}:
            return {}

        payload = dict(state.get("action_payload", {}))
        board_op = str(payload.get("board_op", "upsert")).strip().lower()
        session_id = state["session_id"]
        item_id = str(payload.get("item_id", "")).strip()

        if board_op == "upsert":
            text = str(payload.get("title") or payload.get("text") or "待补充任务")
            existing = deps.board_store.get_item(session_id, item_id) if item_id else None
            if existing:
                updated = {
                    **existing,
                    "title": text,
                    "scope": payload.get("world_scope", existing.get("scope", "group:main")),
                    "status": str(payload.get("status", existing.get("status", "todo"))),
                    "priority": str(payload.get("priority", existing.get("priority", "medium"))),
                    "due_at": payload.get("due_at", existing.get("due_at")),
                    "owner_id": payload.get("owner_id", existing.get("owner_id", state.get("agent_id"))),
                    "linked_event_id": payload.get("linked_event_id", state.get("focus_reference")),
                    "deleted": False,
                }
                deps.board_store.upsert_item(updated)
                op = {"op": "upsert", "item_id": existing.get("item_id"), "updated": True}
            else:
                item = BoardItem(
                    item_id=item_id or f"b_{uuid4().hex[:10]}",
                    session_id=session_id,
                    scope=str(payload.get("world_scope", "group:main")),
                    title=text,
                    status=str(payload.get("status", "todo")),
                    priority=str(payload.get("priority", "medium")),
                    due_at=payload.get("due_at"),
                    owner_id=payload.get("owner_id") or state.get("agent_id"),
                    linked_event_id=payload.get("linked_event_id") or state.get("focus_reference"),
                )
                deps.board_store.upsert_item(item.to_dict())
                op = {"op": "upsert", "item_id": item.item_id, "updated": False}
            return {
                "board_operation": op,
                "planned_action": "board_item_upserted",
                "action_payload": {
                    **payload,
                    "board_op": "upsert",
                    "board_operation": op,
                },
            }

        if board_op == "delete" and item_id:
            hard = _as_bool(payload.get("hard_delete", False))
            ok = deps.board_store.delete_item(session_id, item_id, hard=hard)
            op = {"op": "delete", "item_id": item_id, "hard_delete": hard, "ok": ok}
            return {
                "board_operation": op,
                "planned_action": "board_item_deleted",
                "action_payload": {**payload, "board_operation": op},
            }

        if board_op == "archive" and item_id:
            archived = _as_bool(payload.get("archived", True))
            ok = deps.board_store.archive_item(session_id, item_id, archived=archived)
            op = {"op": "archive", "item_id": item_id, "archived": archived, "ok": ok}
            return {
                "board_operation": op,
                "planned_action": "board_item_archived",
                "action_payload": {**payload, "board_operation": op},
            }

        if board_op in {"set_priority", "set_due"} and item_id:
            patch: dict[str, Any] = {}
            if board_op == "set_priority":
                patch["priority"] = str(payload.get("priority", "medium"))
            if board_op == "set_due":
                patch["due_at"] = payload.get("due_at")
            ok = deps.board_store.update_item_fields(session_id, item_id, patch)
            op = {"op": board_op, "item_id": item_id, "patch": patch, "ok": ok}
            mapped_action = "board_item_priority_set" if board_op == "set_priority" else "board_item_due_set"
            return {
                "board_operation": op,
                "planned_action": mapped_action,
                "action_payload": {**payload, "board_operation": op},
            }

        return {
            "board_operation": {"op": "noop", "reason": f"unsupported board_op={board_op}"},
            "errors": [f"board_subgraph: unsupported board_op={board_op}"],
        }

    def board_gc_node(state: AgentState) -> AgentState:
        payload = dict(state.get("action_payload", {}))
        # 待拓展：未来可按时间窗口归档、快照压缩等策略做真正 GC。
        if not _as_bool(payload.get("board_gc", False)):
            return {}
        removed = deps.board_store.gc_items(state["session_id"])
        op = dict(state.get("board_operation", {}))
        op["gc_removed"] = removed
        return {
            "board_operation": op,
            "planned_action": "board_gc_performed",
            "action_payload": {**payload, "board_operation": op},
        }

    graph.add_node("board_read", board_read_node)
    graph.add_node("board_update", board_update_node)
    graph.add_node("board_gc", board_gc_node)
    graph.add_edge(START, "board_read")
    graph.add_edge("board_read", "board_update")
    graph.add_edge("board_update", "board_gc")
    graph.add_edge("board_gc", END)
    return graph.compile()
