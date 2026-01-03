import timestamp

Intention = {
    "intention_id": str,  # UUID，仅用于内部追踪，不是 event_id
    "agent_id": str,  # 站在谁的名义上“想”

    # —— 触发源 ——
    "trigger": {
        "event_id": str,  # 由哪个世界事件引发
        "type": str,  # seen / requested / evaluated / etc.
    },

    # —— 行为原型 ——
    "kind": str,  # 对齐 event.type：speak / submit / evaluation / ...

    # —— 行为草案内容 ——
    "payload": dict,  # 尚未校验、尚未补全的内容
    # 例如 text / result / score / references（候选）

    # —— 意向强度与状态 ——
    "motivation": float,  # 0~1，不是概率，是“我有多想做”
    "confidence": float | None,  # LLM 对自己判断的把握，可选
    "urgency": float | None,  # 是否需要尽快发生（调度用）

    # —— 不确定性标记 ——
    "missing": list[str],  # 还缺哪些关键字段（如 references）
    "risk": list[str],  # 潜在问题：越权 / 重复 / 冲突 / 低价值

    # —— 生命周期控制 ——
    "status": str,  # pending / suppressed / approved / executed / expired
    "created_at": timestamp,
}
