"""LLM 海龟汤 demo：需要环境变量 LLM_ENABLED=1 与 LLM_API_KEY（或 config_data/llm.env）。"""
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
        print("[test_turtle_soup_template_demo] ⚠️ LLM 未启用，设置 LLM_ENABLED=1 后再试。")
        return
    if not settings.llm_api_key:
        print("[test_turtle_soup_template_demo] ⚠️ 未提供 LLM_API_KEY，无法演示。")
        return

    llm_client = build_openai_client_from_settings(settings)
    if llm_client is None:
        print("[test_turtle_soup_template_demo] ⚠️ LLM 客户端未创建成功。")
        return

    boss = Agent("BOSS", role="TurtleSoupHost", expertise=["turtle_soup", "moderation"])
    policeman = Agent("Officer", role="Policeman", expertise=["evidence", "logic"])
    girl = Agent("Lily", role="LittleGirl", expertise=["imagination", "wild_guess"])
    alien = Agent("X-9", role="AlienRobot", expertise=["logic", "probability"])
    doctor = Agent("Dr. Chen", role="DoctorMiss", expertise=["medicine", "psychology"])

    seed = boss.speak(
        "各位欢迎来到海龟汤。玩法说明：你们通过提问来还原谜底，你们可以发表见解，但是也要记得珍惜发言机会进行提问。"
        "我除非主持游戏开始和结束，只能回答『肯定答复 / 否定答复 / 与故事无关』类似陈述句。每轮发言顺序固定为："
        "主持人(0) → 男警察(1) → 主持人(0) → 小女孩(2) → 主持人(0) → 外星人(3) → 主持人(0) → 女医生(4)。"
        "我会在每位玩家提问后给出反馈。最大轮次 30。"
        "本次谜题：《关灯之后》——一个醉酒的男人走进房间，关上灯，随后不久，远处有人死了。为什么？"
    )

    cfg = RuntimeConfig(
        agents=[boss, policeman, girl, alien, doctor],
        policy_path=POLICY_PATH,
        enable_llm=True,
        llm_client=llm_client,
        llm_mode=settings.llm_mode,
        ui_enabled=settings.ui_enabled,
        ui_auto_open=settings.ui_auto_open,
        ui_host=settings.ui_host,
        ui_port=settings.ui_port,
        max_ticks=50,
        seed_events=[seed],
        allow_empty_policy=True,
        scheduler_strategy="template_order",
        scheduler_strategy_config={
            "template": ["0", "1", "0", "2", "0", "3", "0", "4"],
        },
    )

    runtime = bootstrap(cfg)
    runtime.loop.run()

    print("[test_turtle_soup_template_demo] ✅ 演示结束，事件数：", len(runtime.world.events))


if __name__ == "__main__":
    main()
