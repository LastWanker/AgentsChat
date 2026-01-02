# Agents.py
# Agent：系统中最小的“社会行动者”
# 它的唯一职责：以规范化 Event 的形式，对外产生行为。
# Agents.py只负责标注，不负责解释

# 最后一次修改时间：2026年1月2日 16:32:07

from uuid import uuid4
from datetime import datetime, UTC
from typing import List, Optional, TypedDict, Dict, Any, Union


class WeightedReference(TypedDict):
    event_id: str
    weight: float


Reference = Union[str, WeightedReference]


class Agent:
    def __init__(
            self,
            name: str,
            role: str,
            expertise: List[str],
            priority: float = 0.5,
    ):
        # Agent的系统级唯一身份。潜台词是：Agent 可以被销毁、重建、分布式迁移但 id 不依赖数据库、不依赖顺序、不依赖上下文
        self.id = str(uuid4())

        # 在Agent生命周期内不该频繁变化的属性。
        self.name = name
        self.role = role
        self.expertise = expertise

        # 可以临时投票降低某Agent的优先级，但是大多数时候是事后根据结果的优劣和归因算法调整
        self.priority = priority

        # 状态
        self.state = "idle"

        # 可见区域。这不违反公开性，只是公开域不一样。
        self.scope = "public"  # public | group:<id>

        # memory 只存 event_id，不存 event 本体。Agent 不是历史数据库，它只是“知道自己参与过什么”
        self.memory: List[str] = []  # event_ids

        # 显式声明：Agent“知道”自己能干什么，而且应该是时刻被提醒。
        # 这不是为了 Python，而是为了系统反射能力：
        # 调度器可以问：你能不能 evaluation？
        # UI 可以根据这个生成按钮
        # 后续可以做能力裁剪 / 角色限制
        self.available_events = {
            "speak",
            "speak_public",
            "request_specific",
            "request_anyone",
            "request_all",
            "submit",
            "evaluation",
            "state_change",
        }

    # ---------- 基础工具 ----------

    def _new_event(  # “_”表示：这是 Agent 的内部工具，外部不应该直接调用
            self,
            event_type: str,
            content: Dict[str, Any],
            *,  # *,表示一个分隔符，它强制后续的参数必须通过关键字参数（keyword arguments）的方式传递，而不能通过位置参数（positional arguments）传递。
            recipients: Optional[List[str]] = None,
            # references: Optional[List[str]] = None,
            references: Optional[List[Reference]] = None,
            metadata: Optional[Dict[str, Any]] = None,
            completed: bool = True,
    ) -> Dict[str, Any]:

        metadata = metadata or {}
        # scope 决定权：显式 forced_scope > 当前 self.scope
        scope = metadata.get("forced_scope", self.scope)

        event = {
            "event_id": str(uuid4()),
            "type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "sender": self.id,

            "recipients": recipients or [],
            "scope": scope,

            "content": content,
            "references": references or [],
            "metadata": metadata,  # or {},

            "completed": completed,
        }
        # Agent 只负责“我做过什么”，不负责“全局发生了什么”。
        self.memory.append(event["event_id"])

        return event

    # ---------- 社会行为 ----------
    # ---------- 发言行为 ----------
    def speak(self, text: str, references: Optional[List[Reference]] = None):
        # 在当前 scope 发言
        return self._new_event(
            "speak",
            {"text": text},
            references=references,
        )

    def speak_public(self, text: str, references: Optional[List[Reference]] = None):
        # 无条件 public 广播
        return self._new_event(
            "speak_public",
            {"text": text},
            references=references,
            metadata={"forced_scope": "public"},
        )

    # ---------- 请求行为 ----------（一律public）
    def request_specific(self, target_agent_id: str, request: str):
        return self._new_event(
            "request_specific",
            {"request": request},
            recipients=[target_agent_id],
            completed=False,
            metadata={"forced_scope": "public"},
        )

    def request_anyone(self, request: str):
        return self._new_event(
            "request_anyone",
            {"request": request},
            completed=False,
            metadata={"forced_scope": "public"},
        )

    def request_all(self, request: str, rule: Optional[dict] = None):
        return self._new_event(
            "request_all",
            {
                "request": request,
                "rule": rule or {"type": "vote"},
            },
            completed=False,
            metadata={"forced_scope": "public"},
        )

    # ---------- 交付行为 ----------（一律public）
    def submit(
        self,
        result: str,
        references: List[Reference],
        public: bool = False,
    ):
        if not references:
            raise ValueError("submit 必须引用至少一个 request 类 event")

        return self._new_event(
            "submit",
            {"result": result},
            references=references,
            completed=True,
            metadata={
                "forced_scope": "public" if public else self.scope
            },
        )

    # ---------- 评价行为 ----------（天然带符号浮点数的权）
    def evaluation(
            self,
            score: float,
            comment: str,
            references: List[Reference],
    ):
        weighted_refs: List[WeightedReference] = []

        for r in references:
            if isinstance(r, str):
                weighted_refs.append({
                    "event_id": r,
                    "weight": score,
                })
            else:
                weighted_refs.append(r)

        return self._new_event(
            "evaluation",
            {"comment": comment},
            references=weighted_refs,
            completed=True,
        )

    # ---------- 状态变更 ----------（通用）
    def state_change(
        self,
        new_state: str,
        *,
        references: Optional[List[Reference]] = None,
        note: Optional[str] = None,
        completed: bool = False,
        forced_scope: Optional[str] = None,
    ):
        return self._new_event(
            "state",
            {
                "state": new_state,
                "note": note,
            },
            references=references,
            completed=completed,
            metadata={
                "forced_scope": forced_scope
            } if forced_scope else None,
        )

    # ---------- 分组行为 ----------

    def join_group(self, group_id: str, references: List[Reference]):
        """
        宣告：我将加入某个 group
        - 事件发生在进入 group 之前
        - 事件必须是 public
        - 状态变化发生在事件之后
        """

        event = self.state_change(
            "grouped",
            references=references,
            note=f"join group {group_id}",
            completed=False,
            forced_scope="public",
        )

        # 事件之后，世界才真的改变
        self.state = "grouped"
        self.scope = f"group:{group_id}"

        return event

    def leave_group(self, references: List[Reference]):
        """
        宣告：我将离开当前 group
        同样是 public 事件
        """

        event = self.state_change(
            "idle",
            references=references,
            note="leave group",
            completed=False,
            forced_scope="public",
        )

        # 事件之后，回到公共世界
        self.state = "idle"
        self.scope = "public"

        return event
