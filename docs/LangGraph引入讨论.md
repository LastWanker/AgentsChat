# LangGraph 引入讨论（与结构改造统筹版）

## 1. 定位

本文件不再单独讨论“要不要引入”，而是回答：

- 在“项目结构改造”主线下，LangGraph 应该何时进入。
- 进入后替换哪些层，保留哪些层。
- 如何与 `docs/项目结构改造方案.md` 对齐执行。

## 2. 结论

可以引入，而且应采用“分层替换”策略：

- 替换：编排层（workflow engine）。
- 保留：领域模型、业务节点逻辑、事件事实存储。

即：**LangGraph 是流程调度内核，不是整仓重写理由。**

## 3. 与结构改造的对齐关系

前置条件（必须先完成）：

1. 已有 `workflow/engine.py` 抽象（见结构方案 Phase 1）。
2. 业务节点已可函数化复用（`workflow/nodes/*`）。
3. 运行入口支持引擎配置开关。

在此前提下，LangGraph 只需要实现：

- `workflow/langgraph_engine.py`
- `workflow/state.py`
- `workflow/routes/*` 的 LangGraph 路由挂接

当前状态（2026-03-09）：

- `workflow/engine.py`、`workflow/legacy_loop_engine.py`、`workflow/nodes/*`、`workflow/routes/*` 已落地。
- `workflow/langgraph_engine.py` 已落地并接入最小链路。
- 默认引擎已切换到 `langgraph`，未安装依赖时自动回退 `legacy`。
- 依赖声明：`requirements-langgraph.txt`（`langgraph>=1.0.10`）。

## 4. 推荐替换边界

## 4.1 第一批（建议）

- `select_agent`
- `propose_intention`
- `finalize_intention`
- `interpret_and_route`

说明：这 4 段最核心，也最容易做等价性对比。

## 4.2 第二批（谨慎）

- `maintenance_update`（原 SessionMaintenanceObserver）
- 更复杂的人机中断点（HITL interrupt）

说明：涉及副作用与重入，必须在幂等机制明确后再迁。

## 5. 状态与持久化策略

建议双层状态：

1. 业务事实层：`EventStore`（唯一事实源）。
2. 编排状态层：LangGraph checkpoint（thread/tick/node context）。

禁止做法：

- 不要把完整事件历史复制进 checkpoint。
- 不要让 checkpoint 成为事件事实源。

## 6. 风险与控制

1. 节点重跑导致重复写入。
- 控制：外部写操作幂等化；副作用放在可确认节点。

2. 双状态不一致。
- 控制：先写 EventStore，再提交状态推进。

3. 迁移期复杂度上升。
- 控制：保持 `legacy` 可回退；按功能逐段切换。

## 7. 先后顺序（统筹版）

建议顺序如下：

1. 结构改造 Phase 0-1（包化 + 编排解耦）。
2. 结构改造 Phase 2（清理目录与测试组织）。
3. LangGraph 试点（结构方案 Phase 3，对应本文件第一批边界）。
4. 等价性验收通过后，再做默认切换与收敛（结构方案 Phase 4）。

不建议：

- 直接在当前 `runtime/loop.py` 上硬改 LangGraph。
- 在未抽象 workflow engine 前引入大规模图节点。

执行结果（已完成）：

1. Phase 0-2 已完成。
2. Phase 3（LangGraph 试点）已完成。
3. Phase 4（默认切换与收敛）已完成，保留 legacy 回退通道。

## 8. 两周 POC 验收建议

1. legacy 与 langgraph 在同输入下输出事件语义一致。
2. 支持按 `session_id/thread_id` 恢复继续执行。
3. 至少 1 处 interrupt 成功恢复且无重复关键副作用。
4. 可通过配置开关在两种引擎间切换。

## 9. 与结构方案的文档关系

- 结构方案是“主执行计划”。
- 本文是“LangGraph 接入约束与验收补充”。
- 实际排期和任务拆分以结构方案 Phase 为主轴。
