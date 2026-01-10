# main.py
import argparse

from config.settings import load_settings
from llm.client import build_openai_client_from_settings
from runtime.bootstrap import RuntimeConfig, bootstrap
from agents.agent import Agent


def parse_args(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--policy", default="policies/intent_constraint.yaml")
    p.add_argument("--max-ticks", type=int, default=50)
    p.add_argument("--enable-llm", action="store_true", default=None)
    p.add_argument("--disable-llm", action="store_false", dest="enable_llm")
    p.add_argument("--enable-ui", action="store_true", default=None)
    p.add_argument("--disable-ui", action="store_false", dest="enable_ui")
    p.add_argument("--ui-auto-open", action="store_true", default=None)
    p.add_argument("--ui-host", default=None)
    p.add_argument("--ui-port", type=int, default=None)
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
            "enable_ui": args.enable_ui,
            "ui_auto_open": args.ui_auto_open,
            "ui_host": args.ui_host,
            "ui_port": args.ui_port,
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
    settings = load_settings()
    boss, alice, bob = _build_agents()

    seed = boss.request_anyone("请大家给出系统下一步的最小可运行闭环建议")
    print(
        f"[main.py] 🌱 生成种子事件: {seed.get('event_id', '<no-id>')} from {seed.get('sender')}"
    )

    enable_llm = settings.llm_enabled if args.enable_llm is None else args.enable_llm
    llm_client = build_openai_client_from_settings(settings) if enable_llm else None

    enable_ui_arg = getattr(args, "enable_ui", None)
    ui_auto_open_arg = getattr(args, "ui_auto_open", None)
    ui_host_arg = getattr(args, "ui_host", None)
    ui_port_arg = getattr(args, "ui_port", None)

    enable_ui = settings.ui_enabled if enable_ui_arg is None else enable_ui_arg
    ui_auto_open = (
        settings.ui_auto_open if ui_auto_open_arg is None else ui_auto_open_arg
    )
    ui_host = settings.ui_host if ui_host_arg is None else ui_host_arg
    ui_port = settings.ui_port if ui_port_arg is None else ui_port_arg

    cfg = RuntimeConfig(
        agents=[boss, alice, bob],
        policy_path=args.policy,
        enable_llm=enable_llm,
        llm_client=llm_client,
        llm_mode=settings.llm_mode,
        allow_empty_policy=args.allow_empty_policy,
        max_ticks=args.max_ticks,
        data_dir=args.data_dir,
        session_id=args.session_id,
        resume_session_id=args.resume,
        ui_enabled=enable_ui,
        ui_auto_open=ui_auto_open,
        ui_host=ui_host,
        ui_port=ui_port,
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
    if rt.controller.memory:
        print("[main.py] 🧹 等待后台维护任务全部完成…")
        rt.controller.memory.wait_for_maintenance()
        print("[main.py] ✅ 后台维护任务已清空。")
        print("[main.py] 🛑 正在关闭后台维护线程…")
        rt.controller.memory.shutdown()
        print("[main.py] ✅ 后台维护线程已关闭。")
    if rt.ui_server:
        print("[main.py] 🧯 正在关闭 Live UI server…")
        rt.ui_server.shutdown()
        rt.ui_server.server_close()
        print("[main.py] ✅ Live UI server 已关闭。")
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
