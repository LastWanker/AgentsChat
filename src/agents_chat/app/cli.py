from __future__ import annotations

import argparse
import sys

from .bootstrap import RuntimeConfig, build_default_agents
from .runtime import run_session
from ..infrastructure.config import load_settings
from ..infrastructure.llm import build_openai_client_from_settings


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
    p.add_argument("--data-dir", default="data/sessions")
    p.add_argument("--allow-empty-policy", action="store_true")
    p.add_argument("--workflow-engine", default="langgraph", choices=["legacy", "langgraph"])
    session_group = p.add_mutually_exclusive_group()
    session_group.add_argument("--session-id")
    session_group.add_argument("--resume", metavar="SESSION_ID")
    return p.parse_args(argv)


def build_runtime_config(args: argparse.Namespace) -> RuntimeConfig:
    settings = load_settings()
    boss, alice, bob = build_default_agents()
    seed = boss.speak("Please propose the next smallest closed-loop action.")

    enable_llm = settings.llm_enabled if args.enable_llm is None else args.enable_llm
    llm_client = build_openai_client_from_settings(settings) if enable_llm else None

    enable_ui = settings.ui_enabled if args.enable_ui is None else args.enable_ui
    ui_auto_open = settings.ui_auto_open if args.ui_auto_open is None else args.ui_auto_open
    ui_host = settings.ui_host if args.ui_host is None else args.ui_host
    ui_port = settings.ui_port if args.ui_port is None else args.ui_port

    return RuntimeConfig(
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
        seed_events=[seed],
        workflow_engine=args.workflow_engine,
    )


def main(argv=None):
    # Windows consoles may default to GBK and crash on emoji logs.
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = parse_args(argv)
    cfg = build_runtime_config(args)
    run_session(cfg)


if __name__ == "__main__":
    main()
