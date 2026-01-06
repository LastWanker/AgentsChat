"""让原先 main.py 的跑法成为测试用例，并加上详细的 debug print。"""

from argparse import Namespace
from pathlib import Path

from main import build_runtime_config, run_session


def _build_args(tmp_path) -> Namespace:
    project_root = Path(__file__).parent.parent
    policy_path = project_root / "policies" / "intent_constraint.yaml"
    args = Namespace(
        policy=str(policy_path),
        max_ticks=8,
        enable_llm=False,
        data_dir=str(tmp_path / "sessions"),
        session_id="test-main-session",
        resume=None,
        allow_empty_policy=True,
    )
    print("[test_main_runtime_flow] 🧭 预设参数:", args)
    return args


def test_main_runtime_end_to_end(tmp_path):
    print("[test_main_runtime_flow] 🧪 开始模拟 main.py 的完整运行。")
    args = _build_args(tmp_path)

    cfg = build_runtime_config(args)
    runtime = run_session(cfg)

    events = runtime.store.all()
    event_ids = [getattr(ev, "event_id", None) for ev in events]
    print(
        f"[test_main_runtime_flow] 📚 store 共记录 {len(events)} 条事件，ID 列表: {event_ids}"
    )

    assert events, "运行后 EventStore 应该至少有一条记录"
    assert runtime.world.events, "World 应该收到过事件并完成广播"

    seed_id = cfg.seed_events[0]["event_id"] if cfg.seed_events else None
    if seed_id:
        world_seed = runtime.world.get_event(seed_id)
        print(
            f"[test_main_runtime_flow] 🌱 查找种子事件 {seed_id}，世界中的结果: {world_seed is not None}"
        )
        assert world_seed, "种子事件应当被写入世界时间线"

    for ag in cfg.agents:
        memory = getattr(ag, "memory", [])
        print(
            f"[test_main_runtime_flow] 🧠 Agent {ag.name} 记忆 {len(memory)} 条，详细: {memory}"
        )
        assert memory, f"Agent {ag.name} 应该观察到至少一条事件"

    print(
        f"[test_main_runtime_flow] ✅ 世界事件总数 {len(runtime.world.events)}，已验证基本闭环。"
    )