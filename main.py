# main.py
import argparse
from runtime.bootstrap import RuntimeConfig, bootstrap
from agents.agent import Agent


def parse_args(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--policy", default="policies/intent_constraint.yaml")
    p.add_argument("--max-ticks", type=int, default=50)
    p.add_argument("--enable-llm", action="store_true")
    p.add_argument("--data-dir", default="data/sessions", help="session 落盘目录")
    p.add_argument(
        "--allow-empty-policy",
        action="store_true",
        help="在未安装 PyYAML 时允许空策略运行（仅用于快速测试）",
    )
    session_group = p.add_mutually_exclusive_group()
    session_group.add_argument("--session-id", help="强制指定新 session_id")
    session_group.add_argument("--resume", metavar="SESSION_ID", help="恢复指定 session")
    args = p.parse_args(argv)
    print(
        "[main.py] 🧭 解析到的参数:",
        {
            "policy": args.policy,
            "max_ticks": args.max_ticks,
            "enable_llm": args.enable_llm,
            "data_dir": args.data_dir,
            "session_id": args.session_id,
            "resume": args.resume,
            "allow_empty_policy": args.allow_empty_policy,
        },
    )
    return args


def _build_agents():
    print("[main.py] 🤖 准备创建默认的三人小队：BOSS/Alice/Bob。")
    boss = Agent("BOSS", role="boss", expertise=["authority"])
    alice = Agent("Alice", role="thinker", expertise=["logic"])
    bob = Agent("Bob", role="critic", expertise=["debate"])
    for ag in (boss, alice, bob):
        print(
            f"[main.py]   ↳ Agent {ag.name} (role={ag.role}, expertise={ag.expertise}, id={ag.id}) 已就绪。"
        )
    return boss, alice, bob


def build_runtime_config(args: argparse.Namespace) -> RuntimeConfig:
    boss, alice, bob = _build_agents()

    seed = boss.request_anyone("请大家给出系统下一步的最小可运行闭环建议")
    print(
        f"[main.py] 🌱 生成种子事件: {seed.get('event_id', '<no-id>')} from {seed.get('sender')}"
    )

    cfg = RuntimeConfig(
        agents=[boss, alice, bob],
        policy_path=args.policy,
        enable_llm=args.enable_llm,
        allow_empty_policy=args.allow_empty_policy,
        max_ticks=args.max_ticks,
        data_dir=args.data_dir,
        session_id=args.session_id,
        resume_session_id=args.resume,
        agent_cooldowns_sec={
            "Alice": 1.5,
            "Bob": 1.5,
        },
        inter_event_gap_sec=1.0,
        seed_events=[seed],
    )

    print(
        "[main.py] 🛠️ RuntimeConfig 已创建:",
        {
            "policy_path": cfg.policy_path,
            "max_ticks": cfg.max_ticks,
            "data_dir": cfg.data_dir,
            "session_id": cfg.session_id,
            "resume_session_id": cfg.resume_session_id,
            "cooldowns": cfg.agent_cooldowns_sec,
            "seed_events": len(cfg.seed_events or []),
        },
    )
    return cfg


def run_session(cfg: RuntimeConfig):
    print("[main.py] 🚀 开始 bootstrap，搭建完整运行时…")
    rt = bootstrap(cfg)
    print(
        f"[main.py] 🧩 bootstrap 完成，世界已有观察者 {len(rt.world.observers)} 个，store session={rt.store.session_id}。"
    )
    print(
        f"[main.py] 🔄 即将以 max_ticks={cfg.max_ticks} 运行 loop，当前 world.events={len(rt.world.events)}。"
    )
    rt.loop.run()
    print(
        f"[main.py] 🏁 运行结束：world.events={len(rt.world.events)}，store 总事件={len(rt.store.all())}。"
    )
    for ag in cfg.agents:
        print(
            f"[main.py] 🧠 Agent {ag.name} 记忆 {len(getattr(ag, 'memory', []))} 条: {getattr(ag, 'memory', [])}"
        )
    return rt


def main():
    args = parse_args()
    cfg = build_runtime_config(args)
    run_session(cfg)


if __name__ == "__main__":
    main()
