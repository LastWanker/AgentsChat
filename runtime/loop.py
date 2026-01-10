import time

from events.intention_finalizer import IntentionFinalizer
from events.intention_schemas import IntentionDraft
from events.tagging import generate_tags


class RuntimeLoop:
    def __init__(
        self,
        controller,
        scheduler,
        router,
        max_ticks: int = 50,
        finalizer: IntentionFinalizer | None = None,
        idle_wait_sec: float = 10.0,
    ):
        self.controller = controller
        self.scheduler = scheduler
        self.router = router
        self.max_ticks = max_ticks
        self._tick_index = 0
        self.finalizer = finalizer
        self.idle_wait_sec = idle_wait_sec

    def tick(self):
        start_time = time.monotonic()
        agent, wait_sec = self.scheduler.choose_agent(self.controller.agents, loop_tick=self._tick_index)
        if agent is None:
            if wait_sec is not None and wait_sec > 0:
                print(
                    f"[runtime/loop.py] ⏸️ 没有可调度 Agent，等待 {wait_sec:.2f}s。"
                )
                time.sleep(wait_sec)
                self._sleep_to_tick_gap(start_time)
                return True
            print(
                f"[runtime/loop.py] ⏳ 暂无 Agent 可调度，等待 {self.idle_wait_sec:.2f}s。"
            )
            if self.idle_wait_sec > 0:
                time.sleep(self.idle_wait_sec)
            self._sleep_to_tick_gap(start_time)
            return True

        draft = self.controller.propose_for_agent(agent)
        if draft is None:
            print(
                f"[runtime/loop.py] 💤 {agent.name} 没有可用草稿，跳过本轮。"
            )
            self.scheduler.record_turn(agent.id, loop_tick=self._tick_index)
            self._tick_index += 1
            self._sleep_to_tick_gap(start_time)
            return True

        print(
            f"[runtime/loop.py] 🎯 轮到 {agent.name} 的草稿 {draft.intention_id}，类型是 {draft.kind}。"
        )

        should_finalize = self._should_finalize(draft)
        if not should_finalize:
            print(
                f"[runtime/loop.py] 💤 {agent.name} 意愿评分不足，发布“兴趣缺缺”声明。"
            )
            from events.types import Intention

            intention_for_router = Intention(
                intention_id=draft.intention_id,
                agent_id=agent.id,
                kind="speak",
                payload={"text": f"{agent.name}对讨论兴趣缺缺，跳过了这次发言。"},
                references=[],
                tags=self._fallback_tags(agent, draft),
                confidence=draft.confidence,
                motivation=draft.motivation,
                urgency=draft.urgency,
            )
        else:
            if self.finalizer is None:
                raise RuntimeError("RuntimeLoop 缺少 finalizer，无法处理 IntentionDraft。")
            print(
                f"[runtime/loop.py] 🔍 草稿 {draft.intention_id} 进入两段式流程：先交给 finalizer 解析引用再路由。"
            )
            intention_for_router = self.finalizer.finalize(
                draft, agent_id=agent.id, intention_id=draft.intention_id
            )
            print(
                f"[runtime/loop.py] ✅ 草稿 {draft.intention_id} 完成 final 阶段，已转换成可路由的意向。"
            )

        self.router.handle_intention(intention_for_router, agent, tick_index=self._tick_index)
        self.scheduler.record_turn(agent.id, loop_tick=self._tick_index)
        self._tick_index += 1
        self._sleep_to_tick_gap(start_time)
        return True

    @staticmethod
    def _should_finalize(draft: IntentionDraft) -> bool:
        score = draft.confidence + draft.motivation + draft.urgency
        return score > 1.0 or max(draft.confidence, draft.motivation, draft.urgency) > 0.5

    def run(self, max_ticks: int | None = None):
        total_ticks = max_ticks if max_ticks is not None else self.max_ticks
        print(f"[runtime/loop.py] ▶️ 开始循环跑 {total_ticks} 轮，看看会发生什么。")
        for _ in range(total_ticks):
            progressed = self.tick()
            if not progressed:
                print("[runtime/loop.py] 💤 没有新的意向要处理，提前收工。\n")
                break
        else:
            print("[runtime/loop.py] 🔚 达到最大轮次，先收一收。\n")
        if getattr(self.controller, "memory", None):
            print("[runtime/loop.py] 🧹 等待后台维护任务全部完成…")
            drained = self.controller.memory.wait_for_maintenance()
            if drained:
                print("[runtime/loop.py] ✅ 后台维护任务已清空。")
            else:
                print("[runtime/loop.py] ⚠️ 后台维护任务未能完全清空。")

    @staticmethod
    def _fallback_tags(agent, draft: IntentionDraft) -> list[str]:
        domain = getattr(agent, "expertise", []) or []
        fixed = [
            str(getattr(agent, "name", agent.id)),
            str(domain[0] if domain else getattr(agent, "role", "general")),
        ]
        text = draft.draft_text or draft.message_plan
        return generate_tags(text=text, fixed_prefix=fixed, max_tags=6)

    @staticmethod
    def _sleep_to_tick_gap(start_time: float, gap_sec: float = 1.0) -> None:
        elapsed = time.monotonic() - start_time
        if elapsed < gap_sec:
            time.sleep(gap_sec - elapsed)
