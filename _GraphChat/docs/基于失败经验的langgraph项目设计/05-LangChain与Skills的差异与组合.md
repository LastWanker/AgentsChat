# 05 LangChain 与 Skills 的差异与组合

## 1. 先给结论

- `LangChain`：偏“能力编排库”，提供模型、提示词、工具、检索器等构件。
- `LangGraph`：偏“状态机运行时”，负责节点、路由、持久化、中断恢复。
- `Skills`：偏“能力包/领域插件”，通常是结构化输入输出 + 工具调用 + 规则约束的组合。

你的项目里最推荐的是：

- `LangGraph` 管流程与状态边界。
- `LangChain` 提供节点内的模型/检索/工具能力。
- `Skills` 作为动作节点可调用的可复用能力单元。

## 2. 差异对照（结合你的场景）

| 维度 | LangChain | Skills | 你项目中的角色 |
|---|---|---|---|
| 本质 | 组件与调用抽象层 | 领域能力封装层 | 给 Agent 提供“会做什么” |
| 关注点 | 如何调用模型/工具/检索器 | 在某个任务上怎么稳定执行 | `web_search`、`share_file`、`grouping` |
| 状态机能力 | 弱（可串联，但不强调图状态） | 通常没有独立状态机 | 需由 LangGraph 托管 |
| 持久化与恢复 | 非核心 | 非核心 | 用 LangGraph checkpoint + 本地存储 |
| 中断与人工介入 | 非主能力 | 非主能力 | 用 LangGraph `interrupt/resume` |
| 输出约束 | 可做 schema | 可内置 schema | 最终由图节点验证并执法 |

## 3. 你可以把 Skills 设计成什么

建议 Skill 最低包含：

- `skill_id`
- `input_schema`
- `output_schema`
- `policy_requirements`
- `executor`（工具调用逻辑）
- `fallback`（失败降级策略）

示例：

- `skill_grouping`: 创建分组、拉人、广播分组目标。
- `skill_web_research`: 联网检索并产出结构化证据。
- `skill_file_exchange`: 共享文件、提取摘要、写回引用。

## 4. Skill 触发方式（图内）

在 `plan_action` 输出结构化动作：

```json
{
  "action": "search_web",
  "skill_id": "skill_web_research",
  "args": {"query": "LangGraph interrupt best practice"}
}
```

再由 `policy_gate` 校验：

- 当前 Agent 是否有权限用该 skill。
- 是否需要 Boss 批准（如外网访问/文件外发）。
- 是否需要先检索群内证据再联网。

## 5. 为什么不能只靠 Skills

因为你的问题本质不是“缺工具”，而是“缺状态边界和执行纪律”。  
Skills 只能提升局部能力，不能替代：

- 独立状态机。
- 中断恢复。
- 事件可追溯。
- 多 Agent 并发协作调度。

这些必须由 LangGraph 或同级运行时负责。
