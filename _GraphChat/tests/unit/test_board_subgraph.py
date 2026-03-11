from __future__ import annotations

from graphchat.application.graphs.subgraphs.board_subgraph import BoardDeps, build_board_subgraph
from graphchat.infrastructure.persistence.board_store import BoardStore


def test_board_subgraph_should_support_upsert_and_archive(tmp_path) -> None:
    store = BoardStore(tmp_path / "sessions")
    graph = build_board_subgraph(BoardDeps(board_store=store))

    create_state = {
        "session_id": "s_board",
        "agent_id": "agent_1",
        "planned_action": "maintain_board",
        "focus_reference": "e_focus",
        "action_payload": {
            "board_op": "upsert",
            "text": "完成API对接",
            "world_scope": "group:main",
            "priority": "high",
            "due_at": "2026-03-20T10:00:00Z",
        },
    }
    created = graph.invoke(create_state)
    op = created.get("board_operation", {})
    item_id = op.get("item_id")
    assert op.get("op") == "upsert"
    assert created.get("planned_action") == "board_item_upserted"
    assert isinstance(item_id, str) and item_id

    item = store.get_item("s_board", item_id)
    assert item is not None
    assert item.get("priority") == "high"
    assert item.get("due_at") == "2026-03-20T10:00:00Z"

    archive_state = {
        "session_id": "s_board",
        "agent_id": "agent_1",
        "planned_action": "maintain_board",
        "action_payload": {"board_op": "archive", "item_id": item_id, "archived": True},
    }
    archived = graph.invoke(archive_state)
    assert archived.get("board_operation", {}).get("op") == "archive"
    assert archived.get("planned_action") == "board_item_archived"
    assert store.get_item("s_board", item_id).get("archived") is True


def test_board_store_soft_delete_and_gc(tmp_path) -> None:
    store = BoardStore(tmp_path / "sessions")
    item = {
        "item_id": "b_delete1",
        "session_id": "s_gc",
        "scope": "group:main",
        "title": "待删除",
        "status": "todo",
        "priority": "medium",
        "due_at": None,
        "archived": False,
        "deleted": False,
        "owner_id": "agent_1",
        "linked_event_id": None,
        "updated_at": "2026-03-11T00:00:00Z",
    }
    store.upsert_item(item)
    assert store.delete_item("s_gc", "b_delete1", hard=False) is True
    assert store.get_item("s_gc", "b_delete1").get("deleted") is True
    removed = store.gc_items("s_gc")
    assert removed == 1
    assert store.get_item("s_gc", "b_delete1") is None
