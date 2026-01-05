# platform/world.py
from dataclasses import asdict, is_dataclass
from typing import List, Dict, Any, Optional


class World:
    def __init__(self):
        # 世界的时间线
        self.events: List[Dict[str, Any]] = []
        self._by_id: Dict[str, Dict[str, Any]] = {}

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
        print(
            f"[platform/world.py] 👂 注册观察者 {getattr(observer, 'id', type(observer).__name__)}，当前总数 {len(self.observers)}。"
        )

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
        event_dict = self._to_dict(event)
        print(
            f"[platform/world.py] 🌐 收到事件 {event_dict.get('event_id', '<no-id>')}，准备通知观察者。"
        )

        # 1. 记录历史（事实不可更改）
        # self.events.append(event)
        self.events.append(event_dict)
        if event_id := event_dict.get("event_id"):
            self._by_id[event_id] = event_dict

        # 2. 按可见性通知观察者
        for observer in self.observers:
            # if self._is_visible(event, observer):
            #     observer.on_event(event)
            if self._is_visible(event_dict, observer):
                print(
                    f"[platform/world.py] 📡 事件 {event_dict.get('event_id', '<no-id>')} 对 {getattr(observer, 'id', type(observer).__name__)} 可见，派发中。"
                )
                observer.on_event(event_dict)

    # ---------- 查询 ----------
    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        return self._by_id.get(event_id)

    # ---------- 工具 ----------
    def _to_dict(self, event: Any) -> Dict[str, Any]:
        if is_dataclass(event):
            return asdict(event)
        if isinstance(event, dict):
            return event
        return getattr(event, "__dict__", {}) or {}
