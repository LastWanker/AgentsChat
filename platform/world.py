# platform/world.py
from typing import List, Dict, Any
# v0.2


class World:
    def __init__(self):
        # 世界的时间线
        self.events: List[Dict[str, Any]] = []

        # 所有观察者（Agent / UI / Logger 都算）
        self.observers: List[Any] = []

    def add_observer(self, observer):
        """
        observer 需要至少有：
        - observer.id
        - observer.scope
        - observer.on_event(event)
        """
        self.observers.append(observer)

    def _is_visible(self, event: Dict[str, Any], observer) -> bool:
        """
        世界唯一的“规则函数”：可见性判断
        """
        event_scope = event.get("scope", "public")
        observer_scope = getattr(observer, "scope", "public")

        # public 事件：所有人可见
        if event_scope == "public":
            return True

        # public 观察者：能看到一切
        if observer_scope == "public":
            return True

        # 同 scope：可见
        return event_scope == observer_scope

    def emit(self, event: Dict[str, Any]):
        """
        世界接收一个已经发生的事件
        """
        # 1. 记录历史（事实不可更改）
        self.events.append(event)

        # 2. 按可见性通知观察者
        for observer in self.observers:
            if self._is_visible(event, observer):
                observer.on_event(event)

