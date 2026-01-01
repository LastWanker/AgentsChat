# Agents.py
# Agent：系统中最小的“社会行动者”
# 它的唯一职责：以规范化 Event 的形式，对外产生行为

from uuid import uuid4
from datetime import datetime
from typing import List, Optional, Dict, Any


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
        self.scope = "public"      # public | group:<id>

        # memory 只存 event_id，不存 event 本体。Agent 不是历史数据库，它只是“知道自己参与过什么”
        self.memory: List[str] = []  # event_ids

        # 显式声明：Agent“知道”自己能干什么，而且应该是时刻被提醒。
        # 这不是为了 Python，而是为了系统反射能力：
        # 调度器可以问：你能不能 evaluation？
        # UI 可以根据这个生成按钮
        # 后续可以做能力裁剪 / 角色限制
        self.available_events = {
            "speak",
            "request_specific",
            "request_anyone",
            "request_all",
            "submit",
            "evaluation",
            "state_change",
        }

    # ---------- 基础工具 ----------

    def _new_event(     # “_”表示：这是 Agent 的内部工具，外部不应该直接调用
        self,
        event_type: str,
        content: Dict[str, Any],
        recipients: Optional[List[str]] = None,
        references: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        event = {
            "event_id": str(uuid4()),
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "sender": self.id,

            "recipients": recipients or [],
            "scope": self.scope,

            "content": content,
            "references": references or [],
            "metadata": {},
        }
        # Agent 只负责“我做过什么”，不负责“全局发生了什么”。
        self.memory.append(event["event_id"])

        return event

    # ---------- 社会行为 ----------

    def speak(self, text: str, references: Optional[List[str]] = None):
        return self._new_event(
            event_type="speak",
            content={"text": text},
            references=references,
        )

    def request_specific(self, target_agent_id: str, request: str):
        return self._new_event(
            event_type="request_specific",
            recipients=[target_agent_id],
            content={"request": request},
        )

    def request_anyone(self, request: str):
        return self._new_event(
            event_type="request_anyone",
            content={"request": request},
        )

    def request_all(self, request: str, rule: Optional[dict] = None):
        return self._new_event(
            event_type="request_all",
            content={
                "request": request,
                "rule": rule or {"type": "vote"}
            },
        )

    def submit(self, result: str, references: List[str]):
        if not references:
            raise ValueError("submit 必须引用至少一个 request event")
        return self._new_event(
            event_type="submit",
            content={"result": result},
            references=references,
        )

    def evaluation(self, score: float, comment: str, references: List[str]):
        return self._new_event(
            event_type="evaluation",
            content={
                "score": score,
                "comment": comment
            },
            references=references,
        )

    def state_change(self, new_state: str, note: Optional[str] = None):
        self.state = new_state
        return self._new_event(
            event_type="state",
            content={
                "state": new_state,
                "note": note
            },
        )

    # ---------- 分组（作用域变化） ----------

    def join_group(self, group_id: str):
        self.scope = f"group:{group_id}"
        return self.state_change("grouped", note=f"join {group_id}")

    def leave_group(self):
        self.scope = "public"
        return self.state_change("idle", note="leave group")
