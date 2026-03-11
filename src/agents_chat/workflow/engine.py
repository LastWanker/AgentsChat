from __future__ import annotations

from typing import Protocol, Any


class WorkflowEngine(Protocol):
    def run(self, max_steps: int | None = None) -> None:
        ...

    def step(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def resume(self, thread_id: str) -> None:
        ...

