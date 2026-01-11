from __future__ import annotations

from typing import Callable, Protocol

from runtime.scheduler_strategies import placeholder, recency, template_order


class SchedulerStrategy(Protocol):
    name: str

    def init_state(self, config: dict | None = None) -> dict:
        ...

    def choose_agent(self, agents: list, state: dict, *, loop_tick: int = 0):
        ...

    def record_turn(self, state: dict, agent_id: str, *, loop_tick: int) -> None:
        ...

    def mark_seed_speakers(
        self,
        state: dict,
        sender_ids: list[str],
        *,
        loop_tick: int = 0,
    ) -> None:
        ...


_STRATEGIES: dict[str, SchedulerStrategy] = {
    recency.name: recency,
    template_order.name: template_order,
    placeholder.name: placeholder,
}


def get_strategy(name: str) -> SchedulerStrategy:
    if name not in _STRATEGIES:
        options = ", ".join(sorted(_STRATEGIES))
        raise ValueError(f"未知调度策略：{name}，可选：{options}")
    return _STRATEGIES[name]


def list_strategies() -> list[str]:
    return sorted(_STRATEGIES)


def resolve_strategy(
    name: str,
    *,
    fallback: Callable[[str], SchedulerStrategy] | None = None,
) -> SchedulerStrategy:
    if fallback is None:
        fallback = get_strategy
    return fallback(name)
