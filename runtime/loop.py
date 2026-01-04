class RuntimeLoop:
    def __init__(self, controller, scheduler, router):
        self.controller = controller
        self.scheduler = scheduler
        self.router = router

    def tick(self):
        it = self.scheduler.choose(self.controller)
        if it is None:
            print(f"[runtime/loop.py] ⏸️ 队列里没人排队，说话暂停。")
            return False

        # 找到对应 agent
        agent = next(a for a in self.controller.agents if a.id == it.agent_id)
        print(
            f"[runtime/loop.py] 🎯 抽中了 {agent.name} 的意向 {it.intention_id}，类型是 {it.kind}。"
        )
        self.router.handle_intention(it, agent)
        return True

    def run(self, max_ticks: int = 50):
        print(f"[runtime/loop.py] ▶️ 开始循环跑 {max_ticks} 轮，看看会发生什么。")
        for _ in range(max_ticks):
            progressed = self.tick()
            if not progressed:
                print("[runtime/loop.py] 💤 没有新的意向要处理，提前收工。\n")
                break
        else:
            print("[runtime/loop.py] 🔚 达到最大轮次，先收一收。\n")
