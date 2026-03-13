from __future__ import annotations

from graphchat.domain.models.schemas import validate_world_command_payload


def test_validate_world_command_payload_should_pass() -> None:
    parsed, err = validate_world_command_payload(
        {
            "command_id": "wc_1",
            "type": "create_agent",
            "session_id": "s1",
            "scope": "group:main",
            "payload": {"agent_id": "agent_9"},
            "priority": 50,
            "created_by": "boss",
            "created_at": "2026-03-11T00:00:00Z",
        }
    )
    assert err is None
    assert parsed is not None
    assert parsed["type"] == "create_agent"


def test_validate_world_command_payload_should_fail_when_type_invalid() -> None:
    parsed, err = validate_world_command_payload(
        {
            "command_id": "wc_2",
            "type": "unknown",
            "session_id": "s1",
            "created_at": "2026-03-11T00:00:00Z",
        }
    )
    assert parsed is None
    assert isinstance(err, str)


def test_validate_world_command_payload_set_agent_retrieval_should_pass() -> None:
    parsed, err = validate_world_command_payload(
        {
            "command_id": "wc_3",
            "type": "set_agent_retrieval",
            "session_id": "s1",
            "scope": "group:main",
            "payload": {"agent_id": "agent_1", "channels": ["web_search", "file_search"]},
            "priority": 50,
            "created_by": "boss",
            "created_at": "2026-03-11T00:00:00Z",
        }
    )
    assert err is None
    assert parsed is not None
    assert parsed["type"] == "set_agent_retrieval"
