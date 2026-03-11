from __future__ import annotations

name = "placeholder"


def init_state(config: dict | None = None) -> dict:
    return {}


def choose_agent(agents: list, state: dict, *, loop_tick: int = 0):
    print("[runtime/scheduler_strategies/placeholder.py] 💤 调度策略占位中，暂不出声。")
    return None, None


def record_turn(state: dict, agent_id: str, *, loop_tick: int) -> None:
    return None


def mark_seed_speakers(state: dict, sender_ids: list[str], *, loop_tick: int = 0) -> None:
    return None
