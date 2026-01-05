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
                continue

            if it.deferred_until_time is not None and now < it.deferred_until_time:
                continue

            print(
                f"[runtime/scheduler.py] 🎲 把 {it.intention_id} 排到前台，由 {it.agent_id} 先上麦。"
            )
            return it

        print("[runtime/scheduler.py] 🙅‍♂️ 队列空空如也，没啥可调度的。")
        return None
