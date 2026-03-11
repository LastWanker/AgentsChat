from __future__ import annotations

from typing import Any, TypedDict
from uuid import uuid4

from .legacy_loop_engine import LegacyLoopEngine


class _GraphState(TypedDict, total=False):
    tick: int
    max_ticks: int
    done: bool
    last_output: dict[str, Any]


class LangGraphEngine:
    """Workflow engine implemented with LangGraph state machine."""

    def __init__(
        self,
        *,
        controller,
        scheduler,
        router,
        max_ticks: int = 50,
        finalizer=None,
        idle_wait_sec: float = 10.0,
        thread_id: str | None = None,
    ) -> None:
        try:
            from langgraph.checkpoint.memory import MemorySaver
            from langgraph.graph import END, StateGraph
        except Exception as exc:  # pragma: no cover - runtime dependency guard
            raise RuntimeError(
                "LangGraph is not installed. Install with: pip install langgraph"
            ) from exc

        self._END = END
        self._StateGraph = StateGraph
        self._MemorySaver = MemorySaver
        self.max_ticks = max_ticks
        self._thread_id = thread_id or f"session-{uuid4().hex[:8]}"
        self._legacy = LegacyLoopEngine(
            controller=controller,
            scheduler=scheduler,
            router=router,
            max_ticks=max_ticks,
            finalizer=finalizer,
            idle_wait_sec=idle_wait_sec,
        )
        self._graph = self._build_graph()

    def _build_graph(self):
        builder = self._StateGraph(_GraphState)
        builder.add_node("tick", self._tick_node)
        builder.set_entry_point("tick")
        builder.add_conditional_edges(
            "tick",
            self._route_next,
            {"tick": "tick", "__end__": self._END},
        )
        return builder.compile(checkpointer=self._MemorySaver())

    def _tick_node(self, state: _GraphState) -> _GraphState:
        result = self._legacy.step()
        tick = int(state.get("tick", 0)) + 1
        max_ticks = int(state.get("max_ticks", self.max_ticks))
        done = tick >= max_ticks or not result.get("progressed", False)
        return {
            "tick": tick,
            "max_ticks": max_ticks,
            "done": done,
            "last_output": result,
        }

    @staticmethod
    def _route_next(state: _GraphState) -> str:
        if state.get("done"):
            return "__end__"
        return "tick"

    def _invoke(self, state: _GraphState | None, *, thread_id: str | None = None):
        tid = thread_id or self._thread_id
        config = {"configurable": {"thread_id": tid}}
        return self._graph.invoke(state, config=config)

    def run(self, max_steps: int | None = None) -> None:
        total = self.max_ticks if max_steps is None else max_steps
        self._invoke({"tick": 0, "max_ticks": total, "done": False})
        if getattr(self._legacy.controller, "memory", None):
            self._legacy.controller.memory.wait_for_maintenance()

    def step(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        max_ticks = int(payload.get("max_ticks", 1))
        out = self._invoke({"tick": 0, "max_ticks": max_ticks, "done": False})
        if isinstance(out, dict):
            return out.get("last_output", out)
        return {"progressed": False}

    def resume(self, thread_id: str) -> None:
        self._thread_id = thread_id
        # Continue from checkpointed state for this thread.
        self._invoke(None, thread_id=thread_id)

