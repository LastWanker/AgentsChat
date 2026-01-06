# AgentsChat（事件驱动多智能体实验场）

围绕“事件-意向”闭环搭建的多智能体协作沙盒。每个 Agent 只声明意向（Intention），由解释器审查后转换为事件（Event），再由世界（World）广播并触发下一轮提案。当前实现专注于规则驱动与基础调度，LLM 接入点与策略文件已预留。

## 系统运行概览

1. **启动入口**：`main.py` 解析命令行，创建 BOSS/Alice/Bob 三人小队，生成一个 `request_anyone` 种子事件，并构建 `RuntimeConfig`。【F:main.py†L3-L90】
2. **装配运行时**：`runtime/bootstrap.py` 依据配置组装世界、事件存储、意向提案器、解释器、路由器、调度器与主循环，并把 Agent/Controller 作为观察者接入世界。【F:runtime/bootstrap.py†L13-L142】【F:runtime/bootstrap.py†L166-L214】
3. **事件触发与观测**：世界记录事件并按可见性通知观察者。AgentObserver 会把可见事件写入 Agent 记忆，AgentController 用它们触发下一轮意向生成。【F:platform/world.py†L6-L61】
4. **意向生成**：Controller 为特定事件选人并调用 `IntentionProposer`。规则模式下，针对请求类事件生成 `submit` 意向，或在允许时对 `speak` 事件给出讨论回复。【F:agents/controller.py†L12-L96】【F:agents/proposer.py†L32-L100】
5. **裁决与路由**：Router 调用 `IntentInterpreter` 按 YAML 策略检查必填字段、引用、禁止条件等；通过后把意向映射为事件并写入存储与世界，期间应用冷却防刷屏。【F:platform/router.py†L36-L104】【F:agents/interpreter.py†L115-L213】
6. **调度循环**：`runtime/loop.py` 逐 tick 从调度器取出等待中的意向，调用 Router 处理；若队列为空则提前结束。【F:runtime/loop.py†L1-L33】

## 核心数据结构

- **Intention**：Agent 的待执行声明，包含 `kind`、`payload`、`scope`、引用等字段，状态字段用于路由与冷却处理。【F:events/types.py†L13-L36】
- **Event**：进入世界的事实记录，包括事件类型、发送方、作用域、内容、引用、接收者及完成状态。【F:events/types.py†L38-L52】
- **Decision**：解释器对意向的裁决结果（approved/suppressed），附带违例列表。【F:events/types.py†L54-L64】
- **Reference**：事件引用格式与权重字段，`normalize_references` 会对 id 进行规范化。【F:events/types.py†L10-L20】【F:events/references.py†L1-L63】

## 组件说明

- **Agent**（`agents/agent.py`）：提供构造各类事件/意向的便捷方法（speak/request/submit 等），并维护记忆、身份、可见域等元数据。【F:agents/agent.py†L1-L152】
- **AgentController**（`agents/controller.py`）：作为世界观察者挑选合适的 Agent 产生意向，并维护待处理队列，可注入事件查询以提供最近/引用上下文。【F:agents/controller.py†L12-L123】【F:agents/controller.py†L131-L183】
- **IntentionProposer**（`agents/proposer.py`）：规则模式默认仅响应请求类事件（submit）或对发言做冷静讨论；预留 LLM 模式入口与冷却/裁剪策略。【F:agents/proposer.py†L32-L116】
- **IntentInterpreter**（`agents/interpreter.py`）：解析 YAML 策略，支持必填字段、引用数量/类型检查，以及禁用表达式的安全求值；允许在未安装 PyYAML 时开启空策略模式。【F:agents/interpreter.py†L77-L143】【F:agents/interpreter.py†L169-L238】
- **Router**（`platform/router.py`）：执行冷却检查、调用解释器、把通过的意向转换为事件写入存储与世界，并记录时间间隔用于节流。【F:platform/router.py†L8-L104】
- **World**（`platform/world.py`）：维护事件时间线与 id 索引，并按作用域向观察者广播。【F:platform/world.py†L6-L58】
- **Scheduler**（`runtime/scheduler.py`）：根据意向状态与冷却字段选择下一条可执行意向，避免提前处理被推迟的项。【F:runtime/scheduler.py†L1-L66】
- **事件存储/查询**：`events/store.py` 将事件持久化到指定数据目录并记录 session 元数据；`events/query.py` 提供最近事件检索用于 proposer。【F:events/store.py†L1-L116】【F:events/query.py†L1-L49】
- **观察者**：`platform/observers.py` 定义基本接口，`ui/console.py` 提供控制台输出示例，`platform/request_tracker.py` 监听请求并在完成时广播对应事件。【F:platform/observers.py†L1-L52】【F:ui/console.py†L1-L49】【F:platform/request_tracker.py†L1-L92】

## 运行与配置

- 依赖：PyYAML 可选，用于解析策略；未安装时可通过 `--allow-empty-policy` 运行空策略。
- 运行示例：
  ```bash
  python main.py --policy policies/intent_constraint.yaml --max-ticks 50 \
    --data-dir data/sessions --enable-llm   # enable_llm 仅打开开关，占位接口
  ```
  日志会展示各阶段装配、意向生成、路由与广播情况。
- Session 与落盘：事件存储默认写入 `data/sessions/<session_id>`，带 metadata 与事件记录；可用 `--session-id` 强制命名或 `--resume` 继续已有 session。【F:runtime/bootstrap.py†L64-L98】【F:events/store.py†L11-L81】
- 策略：`policies/intent_constraint.yaml` 定义意向种类的 require/forbid 规则；其它 YAML 为评估/提案/归因草案，可根据需要扩充。

## 测试与演示

- 快速端到端：`python -m test.test4demo1_without_llm` 会运行无 LLM 的最小闭环。 
- 其它检查：`test/test4agent_observe.py` 验证世界可见性与 Agent 观察行为，`test/test4world.py` 覆盖事件存储与广播，`test/test_main_runtime_flow.py` 跑通装配与循环流程。【F:test/test4demo1_without_llm.py†L1-L68】【F:test/test4agent_observe.py†L1-L59】【F:test/test4world.py†L1-L85】【F:test/test_main_runtime_flow.py†L1-L106】

## 扩展思路

- 在 `agents/proposer.py` 的 `_propose_with_llm` 内接入实际大模型并利用 `ProposerContext` 提供的最近/引用事件上下文。
- 增强冷却与优先级：`platform/router.py` 已有 CooldownGuard，可结合 `RuntimeConfig.agent_cooldowns_sec` 与 `inter_event_gap_sec` 调整节奏。【F:platform/router.py†L8-L34】【F:runtime/bootstrap.py†L103-L128】
- 策略迭代：利用 YAML 规则继续丰富 require/forbid 条件，或在解释器中加入 rewrite/downgrade 逻辑以实现更智能的裁决链。