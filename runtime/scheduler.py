class Scheduler:
    """
    v0.2：按 agent 最近未发言优先进行轮次调度。
    """

    def __init__(self) -> None:
        self._last_turn_tick: dict[str, int] = {}

    def mark_seed_speakers(self, sender_ids: list[str], *, loop_tick: int = 0) -> None:
        for sender_id in sender_ids:
            if sender_id is None:
                continue
            self._last_turn_tick[str(sender_id)] = loop_tick

    def choose_agent(self, agents, *, loop_tick: int = 0):
        if not agents:
            print("[runtime/scheduler.py] 🙅‍♂️ 没有可调度的 Agent。")
            return None, None

        def last_turn(agent_id: str) -> int:
            return self._last_turn_tick.get(agent_id, -1)

        ordered = sorted(agents, key=lambda ag: (last_turn(ag.id), ag.name))
        picked = ordered[0]
        print(
            f"[runtime/scheduler.py] 🎲 轮到 {picked.name} 上麦（最近轮次={last_turn(picked.id)}）。"
        )
        return picked, 0.0

    def record_turn(self, agent_id: str, *, loop_tick: int) -> None:
        self._last_turn_tick[agent_id] = loop_tick
