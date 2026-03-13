from __future__ import annotations

from fastapi.testclient import TestClient

from graphchat.application.runtime import GraphChatRuntime
from graphchat.infrastructure.llm.model_provider import RuleBasedModelProvider
from graphchat.interfaces.api.server import create_app
from graphchat.interfaces.api.settings import APISettings


def _build_test_client(tmp_path, *, api_token: str = "") -> tuple[GraphChatRuntime, TestClient]:
    runtime = GraphChatRuntime(
        base_dir=tmp_path / "data",
        checkpointer_backend="memory",
        model_provider=RuleBasedModelProvider(),
        test_mode=True,
    )
    app = create_app(
        settings=APISettings(
            data_dir=tmp_path / "data",
            checkpointer_backend="memory",
            api_token=api_token,
        ),
        runtime=runtime,
    )
    return runtime, TestClient(app)


def test_api_http_flow_should_support_health_message_and_stream(tmp_path) -> None:
    runtime, client = _build_test_client(tmp_path)
    try:
        with client:
            console = client.get("/internal-console")
            assert console.status_code == 200
            assert "GraphChat Internal Console" in console.text

            health = client.get("/healthz")
            assert health.status_code == 200
            assert health.json().get("status") == "ok"

            ready = client.get("/readyz")
            assert ready.status_code == 200
            assert ready.json().get("status") == "ready"

            post_msg = client.post(
                "/v1/sessions/s_api/messages",
                json={"text": "hello from api"},
            )
            assert post_msg.status_code == 200
            body = post_msg.json()
            assert body.get("session_id") == "s_api"
            assert isinstance(body.get("events"), list)

            with client.stream(
                "GET",
                "/v1/sessions/s_api/stream",
                params={"text": "stream this message"},
            ) as stream_resp:
                assert stream_resp.status_code == 200
                chunks: list[str] = []
                for chunk in stream_resp.iter_text():
                    chunks.append(chunk)
                    if "event: done" in chunk:
                        break
                payload = "".join(chunks)
                assert "event:" in payload
                assert "data:" in payload

            events_resp = client.get("/v1/sessions/s_api/events", params={"limit": 20})
            assert events_resp.status_code == 200
            events_data = events_resp.json()
            assert events_data.get("session_id") == "s_api"
            assert isinstance(events_data.get("events"), list)
    finally:
        runtime.close()


def test_api_http_flow_should_support_world_commands_direct_chat_and_observability(tmp_path) -> None:
    runtime, client = _build_test_client(tmp_path)
    try:
        with client:
            cmd_resp = client.post(
                "/v1/sessions/s_api/world-commands",
                json={
                    "command": {
                        "type": "create_agent",
                        "payload": {"agent_id": "agent_4", "enabled": True},
                    },
                    "created_by": "boss",
                },
            )
            assert cmd_resp.status_code == 200
            cmd_data = cmd_resp.json()
            assert isinstance(cmd_data.get("applied_world_commands"), list)

            direct_resp = client.post(
                "/v1/sessions/s_api/direct-chat",
                json={
                    "agent_id": "agent_1",
                    "text": "status?",
                    "scope": "group:main",
                    "actor_id": "user",
                },
            )
            assert direct_resp.status_code == 200
            direct_event = direct_resp.json().get("event", {})
            assert direct_event.get("action_id") == "direct_reply"
            assert direct_event.get("actor_id") == "agent_1"

            obs_resp = client.get("/v1/sessions/s_api/observability")
            assert obs_resp.status_code == 200
            obs = obs_resp.json()
            assert "pending_approval_count" in obs

            approvals_resp = client.get("/v1/approvals")
            assert approvals_resp.status_code == 200
            approvals = approvals_resp.json()
            assert "count" in approvals
            assert "items" in approvals
    finally:
        runtime.close()


def test_api_http_flow_should_enforce_api_token_when_configured(tmp_path) -> None:
    runtime, client = _build_test_client(tmp_path, api_token="secret-token")
    try:
        with client:
            unauthorized = client.post(
                "/v1/sessions/s_secure/messages",
                json={"text": "hello"},
            )
            assert unauthorized.status_code == 401

            authorized = client.post(
                "/v1/sessions/s_secure/messages",
                json={"text": "hello"},
                headers={"x-api-token": "secret-token"},
            )
            assert authorized.status_code == 200
    finally:
        runtime.close()
