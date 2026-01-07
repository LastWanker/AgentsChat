from events.intention_finalizer import IntentionFinalizer
from events.intention_schemas import IntentionDraft


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
        agent, wait_sec = self.scheduler.choose_agent(self.controller.agents, loop_tick=self._tick_index)
        if agent is None:
            if wait_sec is not None and wait_sec > 0:
                import time

                print(
                    f"[runtime/loop.py] ⏸️ 没有可调度 Agent，等待 {wait_sec:.2f}s。"
                )
                time.sleep(wait_sec)
                return True
            print(
                f"[runtime/loop.py] ⏳ 暂无 Agent 可调度，等待 {self.idle_wait_sec:.2f}s。"
            )
            if self.idle_wait_sec > 0:
                import time

                time.sleep(self.idle_wait_sec)
            return True

        draft = self.controller.propose_for_agent(agent)
        if draft is None:
            print(
                f"[runtime/loop.py] 💤 {agent.name} 没有可用草稿，跳过本轮。"
            )
            self.scheduler.record_turn(agent.id, loop_tick=self._tick_index)
            self._tick_index += 1
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
                scope=draft.target_scope or agent.scope,
                references=[],
                completed=True,
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

        decision = self.router.handle_intention(intention_for_router, agent, tick_index=self._tick_index)
        if decision.status == "suppressed" and any(v.get("kind") == "cooldown" for v in decision.violations):
            print(
                f"[runtime/loop.py] ⏳ {agent.name} 触发冷却，本轮不计入轮次。"
            )
        else:
            self.scheduler.record_turn(agent.id, loop_tick=self._tick_index)
        self._tick_index += 1
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