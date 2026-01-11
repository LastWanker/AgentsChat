# agent.py
from datetime import datetime, UTC
from typing import List, Optional, Dict, Any

from events.id_generator import next_event_id
# 最后一次修改时间：2026年1月6日 16:23:39

"""
Agent 只负责把自己的社会行为记录为 Event。
当前裁剪版本仅保留最基础的发言行为与引用结构，
把复杂流程（请求、评价、分组、冷却等）全部下沉或移除。
"""


from events.references import normalize_references
from events.types import Reference


class Agent:
    _AGENT_ID_COUNTER = 1
    _BOSS_ASSIGNED = False

    def __init__(
            self,
            name: str,
            role: str,
            expertise: List[str],
            priority: float = 0.5,
    ):
        # Agent的系统级唯一身份。潜台词是：Agent 可以被销毁、重建、分布式迁移但 id 不依赖数据库、不依赖顺序、不依赖上下文
        self.id = self._assign_agent_id(name, role)

        # 在Agent生命周期内不该频繁变化的属性。
        self.name = name
        self.role = role
        self.expertise = expertise

        # 可以临时投票降低某Agent的优先级，但是大多数时候是事后根据结果的优劣和归因算法调整
        self.priority = priority

        # 状态
        self.state = "idle"

        # memory 只存 event_id，不存 event 本体。Agent 不是历史数据库，它只是“知道自己参与过什么”
        self.memory: List[str] = []  # event_ids

        # 显式声明：Agent“知道”自己能干什么，而且应该是时刻被提醒。
        # 这不是为了 Python，而是为了系统反射能力：
        # 调度器可以问：你能不能 speak？
        # UI 可以根据这个生成按钮
        # 后续可以做能力裁剪 / 角色限制
        self.available_events = {
            "speak",
        }

    @classmethod
    def _assign_agent_id(cls, name: str, role: str) -> str:
        is_boss = (name or "").upper() == "BOSS" or (role or "").lower() == "boss"
        if is_boss and not cls._BOSS_ASSIGNED:
            cls._BOSS_ASSIGNED = True
            return "0"
        agent_id = str(cls._AGENT_ID_COUNTER)
        cls._AGENT_ID_COUNTER += 1
        return agent_id

    # ---------- 基础工具 ----------
    # Agent.memory 的唯一写入口，是 observe()
    def observe(self, event: dict):
        """
        Agent 看见一个世界事件
        当前版本：只记录，不行动
        """

        event_id = event.get("event_id")
        if event_id:
            self.memory.append(event_id)
            print(
                f"[agents/agent.py] 👁️  Agent {self.name} 记录看到的事件 {event_id}，当前记忆 {len(self.memory)} 条。"
            )

        # self.memory.append({
        #     "seen_event": event["event_id"]
        # })
        # # 现在，要验证的是因果方向是否正确，不是 schema↑ 是否优雅。
        # # 当前这个：{"seen_event": event_id}完全够用，而且它有一个优点：简陋到不可能被误用为事实
        # # 未来我们会真正设计scheme格式，例如下面↓。
        # """
        #         {
        #   "type": "seen_event",
        #   "event_id": "...",
        #   "from": "...",
        #   "timestamp": ...
        # }
        # """

    def _normalize_references(self, references: Optional[List[Reference | str]]) -> List[Reference]:
        """Ensure outgoing references always use the weighted schema."""

        if not references:
            return []
        return normalize_references(references)

    def _new_event(  # “_”表示：这是 Agent 的内部工具，外部不应该直接调用
            self,
            event_type: str,
            content: Dict[str, Any],
            *,  # *,表示一个分隔符，它强制后续的参数必须通过关键字参数（keyword arguments）的方式传递，而不能通过位置参数（positional arguments）传递。
            recipients: Optional[List[str]] = None,
            # references: Optional[List[str]] = None,
            references: Optional[List[Reference | str]] = None,
            metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:

        metadata = metadata or {}
        metadata.setdefault("sender_name", self.name)
        metadata.setdefault("sender_role", self.role)

        event = {
            "event_id": next_event_id(),
            "type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "sender": self.id,

            "recipients": recipients or [],

            "content": content,
            "references": self._normalize_references(references),
            "metadata": metadata,  # or {},
        }

        # Agent 只负责“我做过什么”，不负责“全局发生了什么”。 # 新的变更！统一 memory 的写入口：只允许 observe 写
        # self.memory.append(event["event_id"])  # 写法淘汰。统一 memory 的写入口：只允许 observe 写，详见上面的observe类

        return event

    # ---------- 社会行为 ----------
    # ---------- 发言行为 ----------
    def speak(self, text: str, references: Optional[List[Reference | str]] = None):
        return self._new_event(
            "speak",
            {"text": text},
            references=references,
        )
