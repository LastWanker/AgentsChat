import timestamp

Intention = {
    "intention_id": str,  # UUID，仅用于内部追踪，不是 event_id
    "agent_id": str,  # 站在谁的名义上“想”

    # —— 行为原型 ——
    "kind": str,  # 对齐 event.type：speak / ...

    # —— 行为草案内容 ——
    "payload": dict,  # 例如 text

    # —— 引用信息 ——
    "references": list,  # 最终引用（全局事件图骨架）

    # —— 意向强度 ——
    "motivation": float,  # 0~1，不是概率，是“我有多想做”
    "confidence": float | None,  # LLM 对自己判断的把握，可选
    "urgency": float | None,  # 是否需要尽快发生（调度用）

    # —— 不确定性标记 ——
    "missing": list[str],  # 还缺哪些关键字段（如 references）
    "risk": list[str],  # 潜在问题：重复 / 冲突 / 低价值

    # —— 生命周期控制 ——
    "created_at": timestamp,
}
