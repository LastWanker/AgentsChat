# _GraphChat 项目经历（技术与设计导向，简历版）

> 更新时间：2026-03-12  
> 适用场景：技术简历、项目答辩、面试项目讲解。  
> 项目定位：从根目录原生态多 Agent 实验工程（`AgentsChat`）演进为可内部使用的 LangGraph 多 Agent 应用（`_GraphChat`）。

## 1. 一句话项目描述（简历可用）

主导将早期事件驱动多 Agent 原型重构为分层清晰、状态机可观测、支持审批中断恢复与 Web 控制台操作的 LangGraph Planner-Executor 系统，并完成从脚本化运行到内部 APP 化的核心闭环。

## 2. 背景与问题（前身项目提要）

前身 `AgentsChat` 已具备“Intention -> Interpreter -> Router -> World”的实验闭环与双引擎（`langgraph`/`legacy`）兼容能力，但在“可持续演进”为应用形态时存在典型问题：

- 编排与业务实现耦合偏高，新增能力时容易触及主流程。
- 图语义与运行语义不完全对齐，执行阶段不够显式。
- 面向非开发者的入口不足，主要依赖 CLI/demo 脚本。

## 3. 我的技术设计与核心实现

### 3.1 架构重塑：从实验工程到分层状态机应用

- 在 `_GraphChat/src/graphchat` 采用 `domain -> application -> infrastructure -> interfaces` 分层，建立清晰依赖边界。
- 以 `world_graph + agent_graph` 双图组织协作与单 Agent 生命周期，核心编排集中在 `application/graphs`。
- 将图元信息结构化输出到 `graph_bundle + graph_viewer`，支持静态边、条件边、Send 分发、loop 的统一可视化。

### 3.2 Planner-Executor 演进：执行成为显式状态机阶段

- M7：将 agent 主图收敛到计划驱动，不再显式写死 `retrieval/board/governance` 顺序，改为 action 计划语言驱动（`actions[]/depends_on/priority/dispatch`）。
- M8：把执行阶段从编排阶段显式拆出，主链路升级为：  
  `plan_action -> action_parallel_subgraph(plan only) -> skill_execution_subgraph -> lifecycle_gate`。
- 在 `skill_execution_subgraph` 中以 `Send` 分发到离散 skill lane（`skill_rag/skill_board/skill_governance/skill_dialog/skill_generic`），并行执行后合并汇总。

### 3.3 治理与安全：每个 Skill 独立 Guard 策略

- 将 guard 从全局固定串改为“按 action 绑定 profile”，支持默认策略与运行时 patch（`set_skill_guard_profile`）。
- 执行层按 profile 决定 citation/policy/schema/registry/idempotency guard 是否启用。
- 通过 `plan_execution_report`（`completed/remaining_steps/...`）给出可判定的执行完成语义，而不是仅依赖图边推断。

### 3.4 可扩展控制面：World 命令处理插件化

- 把 World 命令实现从节点编排中解耦到 `command_handlers`，通过依赖注入扩展命令能力。
- 支持 `create_agent / upsert_group / set_agent_retrieval / direct_chat / force_phase` 等控制面能力，提升“增功能不改主骨架”的可维护性。

### 3.5 APP 化落地：从 Runtime/CLI 到内部 Web 可用

- 新增 FastAPI 服务入口与健康检查（`/healthz`、`/readyz`），并提供 `/v1` 业务接口与 SSE 流式通道。
- 提供内部控制台 `internal_console.html`，覆盖消息交互、审批处理、world command、direct chat、observability。
- UI 支持中英文切换，默认中文（`lang=zh`），降低非开发者上手成本。

## 4. 可量化结果（截至 2026-03-12）

- 里程碑：M0-M8 已完成，M9（内部 APP 化）进行中，A-D 已落地，E 收口中。
- 测试回归：`pytest -c _GraphChat/pytest.ini _GraphChat/tests` 当前 `43 passed`。
- 工程规模：`_GraphChat/src/graphchat` Python 文件约 68 个；`_GraphChat/tests` 测试文件 48 个。
- 对比前身：根目录原始 `src/agents_chat` 约 61 个 Python 文件、`tests/` 44 个测试文件，重构后在能力扩展同时保持测试覆盖持续增长。

## 5. 简历可直接粘贴版本（精简）

- 主导多 Agent 系统从原型工程向应用化重构：建立 `domain/application/infrastructure/interfaces` 分层，形成 `world_graph + agent_graph` 双状态机架构。  
- 设计并落地 Planner-Executor：将主图固定 action 链改为计划语言驱动，并通过显式 `skill_execution_subgraph` 实现并行 skill 执行与可观测闭环。  
- 实现按 Skill 配置化 Guard 策略（运行时可调），把治理能力从“全局串”升级为“动作级策略”，并以 `plan_execution_report` 提供执行完成判定。  
- 完成内部 APP 化核心链路：FastAPI + SSE + internal console，支持消息、审批、world command、direct chat、observability，一线非开发者可直接使用。  
- 推动工程质量闭环：持续补齐单元/集成测试，当前 `_GraphChat` 全量回归 `43 passed`（2026-03-12）。

## 6. 技术关键词（ATS/面试关键词）

`Python` `LangGraph` `LangChain` `StateGraph` `FastAPI` `SSE` `Planner-Executor` `Multi-Agent` `Guardrails` `Observability` `Checkpointer` `Event-driven` `DDD-like layering`
