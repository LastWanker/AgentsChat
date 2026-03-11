from __future__ import annotations

from runtime.scheduler_strategies import SchedulerStrategy
from runtime.scheduler_strategies import recency


class Scheduler:
    """
    可替换调度器：由具体策略模块决定下一个发言者。
    """

    def __init__(
        self,
        strategy: SchedulerStrategy | None = None,
        *,
        strategy_config: dict | None = None,
    ) -> None:
        self._strategy = strategy or recency
        self._state = self._strategy.init_state(strategy_config)

    @property
    def strategy_name(self) -> str:
        return getattr(self._strategy, "name", "<unknown>")

    def mark_seed_speakers(self, sender_ids: list[str], *, loop_tick: int = 0) -> None:
        self._strategy.mark_seed_speakers(self._state, sender_ids, loop_tick=loop_tick)

    def choose_agent(self, agents, *, loop_tick: int = 0):
        return self._strategy.choose_agent(agents, self._state, loop_tick=loop_tick)

    def record_turn(self, agent_id: str, *, loop_tick: int) -> None:
        self._strategy.record_turn(self._state, agent_id, loop_tick=loop_tick)
