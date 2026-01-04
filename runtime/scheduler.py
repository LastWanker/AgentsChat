class Scheduler:
    """
    v0：最蠢的调度器——先来先服务。
    """
    def choose(self, controller):
        return controller.pop_one()
