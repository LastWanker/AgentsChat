from __future__ import annotations

import os
import sys
import types

from graphchat.infrastructure.llm.model_provider import (
    LangChainStructuredModelProvider,
    RuleBasedModelProvider,
    build_model_provider,
)


def test_build_model_provider_without_env_should_use_rule_based(monkeypatch) -> None:
    monkeypatch.delenv("GRAPHCHAT_MODEL", raising=False)
    monkeypatch.delenv("GRAPHCHAT_MODEL_PROVIDER", raising=False)

    provider = build_model_provider(allowed_actions={"speak", "search_web"})
    assert isinstance(provider, RuleBasedModelProvider)
    plan = provider.plan_action(
        {
            "last_event": {
                "payload": {
                    "text": "请帮我查一下最新文档",
                }
            }
        }
    )
    assert plan.get("action") == "search_web"
    assert plan.get("payload", {}).get("world_scope") == "group:main"


def test_build_model_provider_deepseek_without_adapter_should_fallback(monkeypatch) -> None:
    monkeypatch.setenv("GRAPHCHAT_MODEL", "deepseek-chat")
    monkeypatch.setenv("GRAPHCHAT_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("GRAPHCHAT_DEEPSEEK_API_KEY", "sk-local-test")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "langchain_deepseek", None)
    monkeypatch.setitem(sys.modules, "langchain_openai", None)

    provider = build_model_provider(allowed_actions={"speak", "search_web"})
    assert isinstance(provider, RuleBasedModelProvider)


def test_build_model_provider_deepseek_with_openai_compat_stub(monkeypatch) -> None:
    monkeypatch.setenv("GRAPHCHAT_MODEL", "deepseek-chat")
    monkeypatch.setenv("GRAPHCHAT_MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("GRAPHCHAT_DEEPSEEK_API_KEY", "sk-local-test")
    monkeypatch.setenv("GRAPHCHAT_DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "langchain_deepseek", None)

    fake_module = types.ModuleType("langchain_openai")

    class _Parsed:
        action = "speak"
        payload = {"text": "ok", "world_scope": "group:main"}

    class _FakeStructuredLLM:
        def invoke(self, _messages):
            return _Parsed()

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def with_structured_output(self, _schema):
            return _FakeStructuredLLM()

    fake_module.ChatOpenAI = FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)

    provider = build_model_provider(allowed_actions={"speak", "search_web"})
    assert isinstance(provider, LangChainStructuredModelProvider)
    assert os.getenv("DEEPSEEK_API_KEY") == "sk-local-test"

    plan = provider.plan_action(
        {
            "last_event": {"payload": {"text": "hello"}},
            "visible_events": [{"event_id": "e1", "payload": {"text": "ctx"}}],
        }
    )
    assert plan["action"] == "speak"
    assert plan["payload"]["world_scope"] == "group:main"
