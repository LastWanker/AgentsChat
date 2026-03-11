import _bootstrap  # noqa: F401

from pathlib import Path

from agents_chat.domain import Agent
from agents_chat.app.bootstrap import RuntimeConfig, build_runtime

ROOT_DIR = Path(__file__).parent.parent
POLICY_PATH = str(ROOT_DIR / "policies" / "intent_constraint.yaml")


def main():
    alice = Agent("Alice", role="thinker", expertise=["logic"])
    bob = Agent("Bob", role="critic", expertise=["debate"])
    boss = Agent("BOSS", role="boss", expertise=["authority"])

    seed = boss.speak("Please discuss the next concrete implementation step.")

    cfg = RuntimeConfig(
        agents=[boss, alice, bob],
        policy_path=POLICY_PATH,
        enable_llm=False,
        allow_empty_policy=True,
        max_ticks=8,
        seed_events=[seed],
        workflow_engine="legacy",
    )
    runtime = build_runtime(cfg)
    runtime.engine.run()
    print("events:", len(runtime.world.events))


if __name__ == "__main__":
    main()
