# 04 HITL 暂停、Boss 介入与流式输入输出

## 1. 暂停与恢复的标准模型

LangGraph 原生支持“可恢复中断”：

- 在节点内调用 `interrupt(payload)` 暂停执行。
- 外部通过 `Command(resume=...)` 恢复。
- 前提是启用 checkpointer。

这正好对应你的“能暂停，让 Boss 介入”的要求。

## 2. Boss 介入协议（事件化）

不要把 Boss 决策藏在控制台输入里，全部事件化：

- `boss_review_requested`
- `boss_feedback_submitted`
- `boss_force_override`
- `boss_resume`

流程：

1. Agent 进入 `policy_gate`，命中高风险规则。
2. 节点 `interrupt(...)` 抛出审查请求，图暂停。
3. Boss 在 UI 提交审批意见，写入事件。
4. 系统用 `Command(resume=...)` 恢复该线程并继续。

## 3. 中断安全（必须处理的坑）

LangGraph 在恢复时会“从该节点开头重跑”。  
因此副作用必须幂等：

- 写事件前先检查 `idempotency_key`。
- 外部工具调用要有去重锁或事务记录。
- `emit_event` 与 `tool_call` 拆分为可重放安全节点。

## 4. 流式输出（模型 token 与节点更新）

推荐并行开两个流：

- `stream_mode="messages"`：token 级输出，给前端实时显示。
- `stream_mode="updates"`：节点级状态更新，给调试和观测面板。

也可以混合订阅多个模式，构建“对用户友好 + 对开发可观测”的双视图。

## 5. DeepSeek API 适配结论（校验日期：2026-03-10）

按 DeepSeek 官方文档当前能力：

- Chat Completions 支持 `stream=true`，可做 SSE 流式输出。
- 请求体仍是一次性提交 `messages`，没有官方“逐 token 流式输入”接口。

因此本项目建议：输出走原生流式，输入走事件桥接（`chunk + commit`）模式。

## 6. 输入分片桥接（绕开非流式输入）

### 6.1 输入桥接

`Input Adapter` 把前端分片输入转成两类事件：

- `input_chunk`：临时分片。
- `input_commit`：用户提交（回车/发送）。

### 6.2 图内处理策略

- `input_chunk` 只更新会话草稿态，不触发重决策。
- `input_commit` 才进入 `ingest_events -> route_scope -> dispatch` 主流程。

这能避免“每个字都触发全图重算”。

## 7. 空闲轮询与流式结合

当 Agent 处于 `IdleSilent`：

- 不关闭图线程。
- 按 `poll interval` 拉取新事件窗口。
- 若存在 `@mention`/`boss`/`urgent`，立即转 `Listening`。
- 否则继续静默并更新 `last_heartbeat`。

## 8. 为什么仍需要窗口机制

即使输出是连续流式，图内仍然要做窗口控制：

- 模型每次调用仍有上下文窗口上限。
- 长会话若不裁剪，会带来成本和延迟放大。
- 子图（检索/静默循环）需要可恢复边界，不能无限累积状态。

建议固定策略：`recent_window + board_snapshot + retrieved_evidence`。

## 9. 观测与审计事件

建议把以下过程也写成系统事件：

- `state_transition`
- `interrupt_raised`
- `interrupt_resumed`
- `tool_invoked`
- `stream_started/stream_ended`

这样“行为记录为事件”才完整，不仅是最终发言事件。

## 10. 建议的 UI 面板

最少四块：

- 群聊主时间线（按 scope 过滤）。
- Agent 状态看板（每个 Agent 当前节点/状态）。
- Boss 审批队列（待恢复线程）。
- 引用溯源面板（本次输出引用了哪个主事件，为什么）。
