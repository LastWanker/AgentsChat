# agents/controller.py
# 最后一次修改时间：2026-01-04
"""
Controller 的定位（v0.1）：

Controller 不是智能体，
不是策略引擎，
不是世界本身。

它的唯一职责是：
    在“某个 Event 已经发生”之后，
    决定：
        是否允许、以及由谁，
        触发下一个 Event。

Controller 是因果的闸门，而不是思考的源头。
"""

from typing import List, Dict, Any, Callable, Optional


class Controller:
    def __init__(self, world, agents: List[Any]):
        """
        world:
            - 负责记录事实与广播事件
        agents:
            - 可被调度的 Agent 实例列表
        """
        self.world = world
        self.agents = {agent.id: agent for agent in agents}

        # 规则注册表（event_type -> handler）
        self.handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}

        self._register_default_handlers()

    # ---------- 对外接口 ----------

    def on_event(self, event: Dict[str, Any]):
        """
        Controller 的唯一入口。

        世界中有新 Event 发生时，
        Controller 被动接收并判断：
            是否需要触发后续行为。
        """
        handler = self.handlers.get(event["type"])
        if handler:
            handler(event)

    # ---------- 规则注册 ----------

    def _register_default_handlers(self):
        """
        v0.1 阶段的最小规则集
        """
        self.handlers = {
            "request_anyone": self._handle_request_anyone,
            # 后续会加：
            # "request_specific"
            # "request_all"
            # "state"
        }

    # ---------- 规则实现 ----------

    def _handle_request_anyone(self, event: Dict[str, Any]):
        """
        广播式请求的最小响应逻辑：

        - completed == False 才有响应意义
        - 选择一个“可回应”的 Agent
        - 允许它发言 / 接单
        """

        if event.get("completed", True):
            return

        candidate = self._select_agent_for_request(event)
        if not candidate:
            return

        # v0.1：只允许一个非常保守的响应——发言确认
        response = candidate.speak(
            text="我可以尝试处理这个请求。",
            references=[event["event_id"]],
        )

        self.world.emit(response)

    # ---------- 选择逻辑（极简） ----------

    def _select_agent_for_request(self, event: Dict[str, Any]):
        """
        v0.1 的选择策略：

        - 排除请求发起者本人
        - 简单按 priority 排序
        - 不考虑能力匹配（刻意留白）
        """

        sender_id = event.get("sender")

        candidates = [
            agent for agent in self.agents.values()
            if agent.id != sender_id
        ]

        if not candidates:
            return None

        # priority 高的优先（简单且可解释）
        candidates.sort(key=lambda a: a.priority, reverse=True)

        return candidates[0]
