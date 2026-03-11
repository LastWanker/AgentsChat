# 03 协议与状态模型（含 DeepSeek 输出 Schema）

## 1. 协议升级目标

把现有 `planned_action` 单动作协议升级为 `actions[]` 多动作协议，同时保持：

- 节点不直接调用供应商 SDK
- 结构化输出 + 强校验
- 兼容 fallback（规则模型）

## 2. 结构化输出协议（模型层）

## 2.1 ActionIntent

```json
{
  "action_id": "speak|maintain_board|vote_decision|...",
  "plan_text": "步骤说明",
  "payload": {},
  "target_scope": "group:main|group:xxx|dm:a:b",
  "target_agents": ["agent_1"],
  "step_index": 1,
  "priority": 10,
  "can_skip": false
}
```

## 2.2 ActionPlanOutput

```json
{
  "reasoning_summary": "简短理由",
  "task_done": false,
  "actions": [/* ActionIntent */]
}
```

约束：

- `actions` 允许为空，但必须给 `task_done`。
- `actions` 允许重复动作。
- `actions` 最大长度 `6`（超过即判为不合规或裁剪）。
- `target_scope` 必须通过 scope schema 校验。
- 默认执行优先级：`board > speak > governance`。
- 若提供 `step_index`，按 `step_index` 执行并覆盖默认优先级。
- `priority` 统一用升序（值越小优先级越高）作为兜底排序键。

## 3. 事件协议扩展

文件：`src/graphchat/domain/models/event.py` / `schemas.py`

新增/规范建议：

- `action_batch_id`（同一轮 actions[] 并行分支关联）
- `phase`（listening/plan/parallel/guardrail/emit）
- `channel`（workflow/direct_chat/system）
- `mentions`（解析后的 mention 列表）

## 4. 生命周期协议

Agent 生命周期枚举：

- `working`
- `idle`
- `sleeping`
- `lastlife`

TTL 语义：

- `global_ttl`: 本次激活生命周期剩余循环预算
- `ttl_renewed`: 是否已续费一次
- `ttl_initial`: V2 初始值 `15`
- `lastlife_threshold`: V2 暂定 `3`

speak 回贴等待窗口：

- `speak_reply_window_seconds`: 默认 `10`
- `test_mode` 下窗口可降为 `1`

## 5. WorldCommand 协议

建议统一 schema，便于 API 和图节点共用：

```json
{
  "command_id": "wc_xxx",
  "type": "create_agent|inject_task|force_phase|...",
  "session_id": "s_xxx",
  "scope": "group:main",
  "payload": {},
  "priority": 50,
  "created_by": "boss|system",
  "created_at": "2026-03-11T00:00:00Z"
}
```

## 6. DeepSeek 官方对齐要求（必须）

1. 模型调用保持无状态：每次请求显式带受控上下文窗口。  
2. `langchain-deepseek` 优先，`langchain-openai(base_url=https://api.deepseek.com)` 回退。  
3. 统一 `with_structured_output(PydanticModel)`，禁止在节点里手写 JSON parser。  
4. 不依赖“隐式会话记忆”；事实源始终是本地 event/checkpoint/board。  

## 7. LangGraph 官方对齐要求（必须）

1. 并行动作必须用 `Send(...)`，不写自定义线程调度器。  
2. 审批与暂停用 `interrupt/resume`，不做自造暂停协议。  
3. 长循环图必须配 `checkpointer`，且设置 `recursion_limit`。  
4. 强制阶段切换通过“状态意图 + 条件路由”，不从外部硬跳 node。  

## 8. 兼容迁移策略

过渡期两套字段共存：

- 新（V2）：`planned_actions`, `action_results`
- 旧（V1）：`planned_action`, `action_payload`

要求：

- 兼容期代码注释必须显式打标签：`V1兼容` / `V2主路径`。

迁移步骤：

1. 先让模型输出新协议，节点内做适配回写旧字段（兼容期）。  
2. 子图全部切到新协议后，移除旧字段依赖。  
3. 最后删除旧 schema 与测试。  
