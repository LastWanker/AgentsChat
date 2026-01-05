# main.py
import argparse
from runtime.bootstrap import RuntimeConfig, bootstrap
from agents.agent import Agent


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--policy", default="policies/intent_constraint.yaml")
    p.add_argument("--max-ticks", type=int, default=50)
    p.add_argument("--enable-llm", action="store_true")
    return p.parse_args()

def main():
    args = parse_args()

    # === 先硬编码一组 agents（后面换成从 config/yaml 读）===
    boss = Agent("BOSS", role="boss", expertise=["authority"])
    alice = Agent("Alice", role="thinker", expertise=["logic"])
    bob = Agent("Bob", role="critic", expertise=["debate"])

    cfg = RuntimeConfig(
        agents=[boss, alice, bob],
        policy_path=args.policy,
        enable_llm=args.enable_llm,
        max_ticks=args.max_ticks,
        agent_cooldowns_sec={
            # BOSS 不限速，其他人比如 2 秒
            "Alice": 2.0,
            "Bob": 2.0,
        },
        inter_event_gap_sec=1.0,
        seed_events=[
            # 让 BOSS 当 seed 发生器：从世界发起第一条请求
            boss.request_anyone("请大家给出系统下一步的最小可运行闭环建议"),
        ],
    )

    rt = bootstrap(cfg)
    rt.loop.run()

if __name__ == "__main__":
    main()
