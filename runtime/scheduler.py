class Scheduler:
    """
    v0.1：先来先服务，但会跳过尚在冷却/延期中的意向。
    """
    def choose(self, controller, *, loop_tick: int = 0):
        import time

        now = time.monotonic()
        for it in controller._queue:
            if it.status != "pending":
                continue

            if it.deferred_until_tick is not None and loop_tick < it.deferred_until_tick:
                print(
                    f"[runtime/scheduler.py] ⚠️ 意向 {it.intention_id} 需等待到 tick {it.deferred_until_tick}，本轮跳过。"
                )
                continue

            if it.deferred_until_time is not None and now < it.deferred_until_time:
                wait = it.deferred_until_time - now
                print(
                    f"[runtime/scheduler.py] ⚠️ 意向 {it.intention_id} 仍在冷却 {wait:.2f}s，本轮不调度。"
                )
                continue

            print(
                f"[runtime/scheduler.py] 🎲 把 {it.intention_id} 排到前台，由 {it.agent_id} 先上麦。"
            )
            return it

        print("[runtime/scheduler.py] 🙅‍♂️ 队列空空如也，没啥可调度的。")
        return None
