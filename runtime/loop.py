class RuntimeLoop:
    def __init__(self, controller, scheduler, router, *, max_ticks: int = 50):
        self.controller = controller
        self.scheduler = scheduler
        self.router = router
        self.max_ticks = max_ticks
        self._tick_index = 0

    def tick(self):
        it, wait_sec = self.scheduler.choose(self.controller, loop_tick=self._tick_index)
        if it is None:
            if wait_sec is not None:
                print(
                    f"[runtime/loop.py] ⏸️ 队列里没人立即可用，但有人在冷却，等待 {wait_sec:.2f}s 再试。"
                )
                if wait_sec > 0:
                    import time

                    time.sleep(wait_sec)
                return True
            print(f"[runtime/loop.py] ⏸️ 队列里没人排队，说话暂停。")
            return False

        # 找到对应 agent
        agent = next(a for a in self.controller.agents if a.id == it.agent_id)
        print(
            f"[runtime/loop.py] 🎯 抽中了 {agent.name} 的意向 {it.intention_id}，类型是 {it.kind}。"
        )
        self.router.handle_intention(it, agent, tick_index=self._tick_index)

        if it.status == "pending":
            # 被冷却/延期，重新排回队尾等待下次调度
            self.controller._queue.append(it)
            print(
                f"[runtime/loop.py] 🔁 意向 {it.intention_id} 因冷却被暂缓，已重新入队等待下一轮。"
            )
        self._tick_index += 1
        return True

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
