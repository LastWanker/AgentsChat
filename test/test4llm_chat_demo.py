"""LLM 群聊 demo：需要环境变量 LLM_ENABLED=1 与 LLM_API_KEY（或 config_data/llm.env）。"""
from pathlib import Path

from agents.agent import Agent
from config.settings import load_settings
from llm.client import build_openai_client_from_settings
from runtime.bootstrap import RuntimeConfig, bootstrap


ROOT_DIR = Path(__file__).parent.parent
POLICY_PATH = str(ROOT_DIR / "policies" / "intent_constraint.yaml")


def main():
    settings = load_settings()
    if not settings.llm_enabled:
        print("[test4llm_chat_demo] ⚠️ LLM 未启用，设置 LLM_ENABLED=1 后再试。")
        return
    if not settings.llm_api_key:
        print("[test4llm_chat_demo] ⚠️ 未提供 LLM_API_KEY，无法演示。")
        return

    llm_client = build_openai_client_from_settings(settings)
    if llm_client is None:
        print("[test4llm_chat_demo] ⚠️ LLM 客户端未创建成功。")
        return

    boss = Agent("BOSS", role="boss", expertise=["authority"])
    alice = Agent("Alice", role="thinker", expertise=["logic"])
    bob = Agent("Bob", role="critic", expertise=["debate"])

    seed = boss.request_anyone("各位好。这次是个测试；你们二位需要就“追求事实正确（Alice的论点）”vs“追求内心通达（Bob的论点）”展开一场辩论。")

    cfg = RuntimeConfig(
        agents=[boss, alice, bob],
        policy_path=POLICY_PATH,
        enable_llm=True,
        llm_client=llm_client,
        llm_mode=settings.llm_mode,
        ui_enabled=settings.ui_enabled,
        ui_auto_open=settings.ui_auto_open,
        ui_host=settings.ui_host,
        ui_port=settings.ui_port,
        max_ticks=12,
        seed_events=[seed],
        allow_empty_policy=True,
    )

    runtime = bootstrap(cfg)
    runtime.loop.run()

    print("[test4llm_chat_demo] ✅ 演示结束，事件数：", len(runtime.world.events))


if __name__ == "__main__":
    main()