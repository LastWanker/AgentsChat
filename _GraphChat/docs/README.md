# _GraphChat 可落地实施文档

本目录是 `_GraphChat` 项目的实施规范，不是概念讨论稿。目标是直接指导开发落地，且全程贴合 LangGraph / LangChain 官方用法。

## 阅读顺序

1. `01-架构总览与分层边界.md`
2. `02-状态机蓝图与子图演进.md`
3. `03-功能层落地方案.md`
4. `04-实施计划与验收标准.md`
5. `05-DeepSeek接入与本地上下文策略.md`
6. `99-官方API对照与约束.md`
7. `工作进度/`：按日期记录搭建与迭代进展
8. `下一步工作计划/`：按日期维护阶段性执行计划
9. `graphs/`：自动导出的状态机可视化产物（bundle + viewer）

## 固定原则

- 分层明确：`domain -> application -> infrastructure -> interfaces`，禁止反向依赖。
- 状态先于 Prompt：所有行为由图状态和契约驱动，不靠自然语言暗示。
- 事件事实源：Event Store 是唯一事实来源；索引、摘要、向量都是可重建层。
- 子图优先：凡是可能复用或会变复杂的状态块，先按“子图就绪”设计。
- 持久化必开：任何需要中断恢复/多轮连续性的图，`compile` 必须配置 `checkpointer`。

## 目录期望（与代码对应）

后续代码目录建议与本文档一致：

```text
_GraphChat/
  src/
    graphchat/
      domain/
      application/
      infrastructure/
      interfaces/
  docs/
    01-架构总览与分层边界.md
    02-状态机蓝图与子图演进.md
    03-功能层落地方案.md
    04-实施计划与验收标准.md
    99-官方API对照与约束.md
```
