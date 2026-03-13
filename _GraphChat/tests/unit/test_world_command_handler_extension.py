from __future__ import annotations

from graphchat.application.nodes.world_nodes import WorldNodeDeps, ingest_world_commands_node
from graphchat.infrastructure.persistence.event_store import JsonlEventStore


def test_world_command_handler_extension_should_work(tmp_path) -> None:
    deps = WorldNodeDeps(
        event_store=JsonlEventStore(tmp_path / "sessions"),
        run_agent=lambda _session_id, _task: [],
        command_handlers={
            "noop_ext": lambda _command, _state, _deps: {"pending_injections": [{"command_id": "noop"}]},
        },
    )
    state = {
        "session_id": "s_ext",
        "world_commands": [
            {
                "command_id": "wc_ext_1",
                "type": "noop_ext",
                "session_id": "s_ext",
                "scope": "group:main",
                "payload": {},
                "priority": 50,
                "created_by": "tester",
                "created_at": "2026-03-12T00:00:00Z",
            }
        ],
    }
    out = ingest_world_commands_node(state, deps)
    assert out.get("pending_injections") == [{"command_id": "noop"}]
    assert out.get("applied_world_commands", [])[0]["type"] == "noop_ext"

