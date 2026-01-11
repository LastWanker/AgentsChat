from __future__ import annotations

name = "template_order"


def init_state(config: dict | None = None) -> dict:
    config = config or {}
    template = config.get("template") or []
    template = [str(item) for item in template]
    return {
        "template": template,
        "cursor": 0,
        "last_turn_tick": {},
    }


def choose_agent(agents: list, state: dict, *, loop_tick: int = 0):
    if not agents:
        print("[runtime/scheduler_strategies/template_order.py] 🙅‍♂️ 没有可调度的 Agent。")
        return None, None

    template = state["template"]
    if not template:
        print(
            "[runtime/scheduler_strategies/template_order.py] "
            "⚠️ 未配置模板顺序，无法调度。"
        )
        return None, None

    agents_by_id = {str(agent.id): agent for agent in agents}
    cursor = state["cursor"]
    for _ in range(len(template)):
        sender_id = template[cursor % len(template)]
        cursor += 1
        if sender_id in agents_by_id:
            picked = agents_by_id[sender_id]
            state["cursor"] = cursor % len(template)
            print(
                "[runtime/scheduler_strategies/template_order.py] "
                f"📌 模板轮到 {picked.name} 上麦（slot={sender_id}）。"
            )
            return picked, 0.0

    print(
        "[runtime/scheduler_strategies/template_order.py] "
        "🙅‍♂️ 模板里没有可用的 Agent。"
    )
    state["cursor"] = cursor % len(template)
    return None, None


def record_turn(state: dict, agent_id: str, *, loop_tick: int) -> None:
    state["last_turn_tick"][agent_id] = loop_tick


def mark_seed_speakers(state: dict, sender_ids: list[str], *, loop_tick: int = 0) -> None:
    for sender_id in sender_ids:
        if sender_id is None:
            continue
        state["last_turn_tick"][str(sender_id)] = loop_tick
