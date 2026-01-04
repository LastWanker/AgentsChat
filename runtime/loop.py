class RuntimeLoop:
    def __init__(self, controller, scheduler, router):
        self.controller = controller
        self.scheduler = scheduler
        self.router = router

    def tick(self):
        it = self.scheduler.choose(self.controller)
        if it is None:
            return False

        # 找到对应 agent
        agent = next(a for a in self.controller.agents if a.id == it.agent_id)
        self.router.handle_intention(it, agent)
        return True

    def run(self, max_ticks: int = 50):
        for _ in range(max_ticks):
            progressed = self.tick()
            if not progressed:
                break
