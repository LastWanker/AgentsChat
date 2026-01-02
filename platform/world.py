# platform/world.py
from typing import List, Dict, Any


class World:
    def __init__(self):
        # 世界才是历史的持有者
        self.events: List[Dict[str, Any]] = []

        # 所有“看世界的人”
        self.observers = []

    def add_observer(self, observer):
        self.observers.append(observer)

    def emit(self, event: Dict[str, Any]):
        """
        世界接收一个已经发生的事件
        """
        # 1. 记录
        self.events.append(event)

        # 2. 通知所有观察者
        for observer in self.observers:
            observer.on_event(event)
