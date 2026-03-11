from __future__ import annotations

name = "recency"


def init_state(config: dict | None = None) -> dict:
    return {"last_turn_tick": {}}


def _last_turn(state: dict, agent_id: str) -> int:
    return state["last_turn_tick"].get(agent_id, -1)


def choose_agent(agents: list, state: dict, *, loop_tick: int = 0):
    if not agents:
        print("[runtime/scheduler_strategies/recency.py] 🙅‍♂️ 没有可调度的 Agent。")
        return None, None

    ordered = sorted(agents, key=lambda ag: (_last_turn(state, ag.id), ag.name))
    picked = ordered[0]
    print(
        "[runtime/scheduler_strategies/recency.py] "
        f"🎲 轮到 {picked.name} 上麦（最近轮次={_last_turn(state, picked.id)}）。"
    )
    return picked, 0.0


def record_turn(state: dict, agent_id: str, *, loop_tick: int) -> None:
    state["last_turn_tick"][agent_id] = loop_tick


def mark_seed_speakers(state: dict, sender_ids: list[str], *, loop_tick: int = 0) -> None:
    for sender_id in sender_ids:
        if sender_id is None:
            continue
        state["last_turn_tick"][str(sender_id)] = loop_tick
