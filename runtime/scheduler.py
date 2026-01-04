class Scheduler:
    """
    v0：最蠢的调度器——先来先服务。
    """
    def choose(self, controller):
        # return controller.pop_one()
        intention = controller.pop_one()
        if intention is None:
            print("[runtime/scheduler.py] 🙅‍♂️ 队列空空如也，没啥可调度的。")
        else:
            print(
                f"[runtime/scheduler.py] 🎲 把 {intention.intention_id} 排到前台，由 {intention.agent_id} 先上麦。"
            )
        return intention
