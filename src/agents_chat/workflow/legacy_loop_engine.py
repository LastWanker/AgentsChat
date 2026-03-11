from __future__ import annotations

import time
from typing import Any

from events.intention_finalizer import IntentionFinalizer

from .nodes.turn import build_fallback_intention, choose_turn_agent
from .routes.finalization import should_finalize


class LegacyLoopEngine:
    """Phase-1 compatibility engine extracted from runtime.loop."""

    def __init__(
        self,
        *,
        controller,
        scheduler,
        router,
        max_ticks: int = 50,
        finalizer: IntentionFinalizer | None = None,
        idle_wait_sec: float = 10.0,
    ) -> None:
        self.controller = controller
        self.scheduler = scheduler
        self.router = router
        self.max_ticks = max_ticks
        self._tick_index = 0
        self.finalizer = finalizer
        self.idle_wait_sec = idle_wait_sec

    def step(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        _ = payload
        start_time = time.monotonic()
        agent, wait_sec = choose_turn_agent(
            self.controller, self.scheduler, self._tick_index
        )
        if agent is None:
            if wait_sec is not None and wait_sec > 0:
                time.sleep(wait_sec)
            elif self.idle_wait_sec > 0:
                time.sleep(self.idle_wait_sec)
            self._sleep_to_tick_gap(start_time)
            return {"progressed": True, "tick": self._tick_index}

        draft = self.controller.propose_for_agent(agent)
        if draft is None:
            self.scheduler.record_turn(agent.id, loop_tick=self._tick_index)
            self._tick_index += 1
            self._sleep_to_tick_gap(start_time)
            return {"progressed": True, "tick": self._tick_index}

        if should_finalize(draft):
            if self.finalizer is None:
                raise RuntimeError("LegacyLoopEngine requires finalizer for draft flow.")
            intention_for_router = self.finalizer.finalize(
                draft, agent_id=agent.id, intention_id=draft.intention_id
            )
        else:
            intention_for_router = build_fallback_intention(agent, draft)

        decision = self.router.handle_intention(
            intention_for_router, agent, tick_index=self._tick_index
        )
        self.scheduler.record_turn(agent.id, loop_tick=self._tick_index)
        self._tick_index += 1
        self._sleep_to_tick_gap(start_time)
        return {
            "progressed": True,
            "tick": self._tick_index,
            "decision_status": getattr(decision, "status", None),
        }

    def run(self, max_steps: int | None = None) -> None:
        total = self.max_ticks if max_steps is None else max_steps
        for _ in range(total):
            out = self.step()
            if not out.get("progressed", False):
                break
        if getattr(self.controller, "memory", None):
            self.controller.memory.wait_for_maintenance()

    def resume(self, thread_id: str) -> None:
        # Compatibility no-op. Kept to match WorkflowEngine protocol.
        print(f"[workflow/legacy_loop_engine.py] resume not needed for thread {thread_id}")

    @staticmethod
    def _sleep_to_tick_gap(start_time: float, gap_sec: float = 1.0) -> None:
        elapsed = time.monotonic() - start_time
        if elapsed < gap_sec:
            time.sleep(gap_sec - elapsed)

