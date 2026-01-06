class Scheduler:
    """
    v0.1：先来先服务，但会跳过尚在冷却/延期中的意向。
    """
    def choose(self, controller, *, loop_tick: int = 0):
        import time

        now = time.monotonic()
        pending_found = False
        min_wait: float | None = None

        pending_found = False
        min_wait: float | None = None

        controller.prune_done()

        for idx, it in enumerate(list(controller._queue)):
            if it.status != "pending":
                continue

            pending_found = True

            if it.deferred_until_tick is not None and loop_tick < it.deferred_until_tick:
                print(
                    f"[runtime/scheduler.py] ⚠️ 意向 {it.intention_id} 需等待到 tick {it.deferred_until_tick}，本轮跳过。"
                )
                # tick 间隔暂定 0.0：由 loop 控制具体等待
                min_wait = 0.0 if min_wait is None else min(min_wait, 0.0)
                continue

            if it.deferred_until_time is not None and now < it.deferred_until_time:
                wait = max(it.deferred_until_time - now, 0.0)
                print(
                    f"[runtime/scheduler.py] ⚠️ 意向 {it.intention_id} 仍在冷却 {wait:.2f}s，本轮不调度。"
                )
                min_wait = wait if min_wait is None else min(min_wait, wait)
                continue

            controller._queue.pop(idx)
            print(
                f"[runtime/scheduler.py] 🎲 把 {it.intention_id} 排到前台，由 {it.agent_id} 先上麦。"
            )
            return it, 0.0

        if pending_found:
            print(
                "[runtime/scheduler.py] ⏳ 队列里都是冷却/延期中的意向，等待下一次重试。"
            )
            return None, min_wait

        print("[runtime/scheduler.py] 🙅‍♂️ 队列空空如也，没啥可调度的。")
        return None, None
