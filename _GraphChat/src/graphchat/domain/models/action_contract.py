from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionSpec:
    action_id: str
    version: str
    scope_limit: str
    approval_policy: str
    citation_policy: str
    needs_retrieval: bool
    enabled: bool = True


def default_action_registry() -> dict[str, ActionSpec]:
    # 待拓展：后续可改为数据库/配置中心动态下发，不改调用层。
    return {
        "speak": ActionSpec("speak", "1.0.0", "group:*", "none", "optional", True),
        "ask_agent": ActionSpec("ask_agent", "1.0.0", "group:*", "none", "optional", False),
        "listen_only": ActionSpec("listen_only", "1.0.0", "group:*", "none", "none", False),
        "search_web": ActionSpec("search_web", "1.0.0", "group:*", "none", "optional", True),
        "request_file": ActionSpec("request_file", "1.0.0", "group:*", "none", "optional", True),
        "share_file": ActionSpec("share_file", "1.0.0", "group:*", "none", "optional", False),
        "create_group": ActionSpec("create_group", "1.0.0", "group:main", "none", "none", False),
        "join_group": ActionSpec("join_group", "1.0.0", "group:*", "none", "none", False),
        "assign_task": ActionSpec("assign_task", "1.0.0", "group:*", "none", "optional", True),
        "vote_decision": ActionSpec("vote_decision", "1.0.0", "group:*", "none", "required_focus", True),
        "dissolve_group": ActionSpec("dissolve_group", "1.0.0", "group:*", "boss_required", "optional", True),
        "maintain_board": ActionSpec("maintain_board", "1.0.0", "group:*", "none", "optional", True),
        "board_item_upserted": ActionSpec("board_item_upserted", "1.0.0", "group:*", "none", "none", False),
        "board_item_deleted": ActionSpec("board_item_deleted", "1.0.0", "group:*", "none", "none", False),
        "board_item_archived": ActionSpec("board_item_archived", "1.0.0", "group:*", "none", "none", False),
        "board_item_priority_set": ActionSpec("board_item_priority_set", "1.0.0", "group:*", "none", "none", False),
        "board_item_due_set": ActionSpec("board_item_due_set", "1.0.0", "group:*", "none", "none", False),
        "board_gc_performed": ActionSpec("board_gc_performed", "1.0.0", "group:*", "none", "none", False),
        "escalate_to_boss": ActionSpec("escalate_to_boss", "1.0.0", "group:*", "none", "optional", False),
    }
