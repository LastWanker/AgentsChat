
> Agent们的聊天群，他们会创造些什么？

这是一个以“事件”为核心的数据驱动多智能体协作实验场。仓库实现了从事件生成、意向提案、解释与路由到世界广播的闭环；配套的 zProposal 文档收录了阶段性规划与设计思考，为后续演进指明路线。以下内容提供当前目录概览、核心概念、运行方式以及里程碑计划。

## 目录总览

| 路径 | 说明 |
| --- | --- |
| `main.py` | 程序入口，启动事件循环与核心组件。 |
| `Intention` | 占位文件，用于表征意向数据结构的命名锚点。 |
| `List[Intention]` | 占位文件，标记“意向列表”类型。 |
| `agents/` | 智能体相关实现（身份、行为、提案、解释、策略）。 |
| `agents/agent.py` | Agent 数据模型与所有事件构造方法（speak、request、submit 等）。 |
| `agents/controller.py` | 处理事件输入、调度提案/动作的控制层。 |
| `agents/proposer.py` | 负责根据触发事件生成意向（包含无 LLM 降级）。 |
| `agents/interpreter.py` | 对意向进行裁决/解释，产出可执行事件。 |
| `agents/policies.py` | Agent 层策略封装与约束定义。 |
| `platform/` | 协作平台内核：世界态、路由与观测接口。 |
| `platform/world.py` | 管理全局事件状态、可见域与广播逻辑。 |
| `platform/router.py` | 事件分发与路由规则，保证唯一事件出口。 |
| `platform/observers.py` | 观察者接口，用于 UI、日志或 Agent 监听。 |
| `platform/observers4debug.py` | 调试友好的观察者实现。 |
| `platform/intention.py` | 意向数据结构与约束。 |
| `events/` | 事件类型与存储、检索接口。 |
| `events/types.py` | 事件协议、字段定义与约束。 |
| `events/store.py` | 事件持久化/缓存接口。 |
| `events/query.py` | 历史事件检索工具。 |
| `llm/` | 大模型接入封装。 |
| `llm/client.py` | LLM API 客户端与降级策略。 |
| `llm/prompts.py` | Prompt 模板与提示工程收集。 |
| `llm/schemas.py` | LLM 输出的结构化校验。 |
| `runtime/` | 运行时循环与调度。 |
| `runtime/loop.py` | 事件驱动主循环，串联 proposer/interpret/router。 |
| `runtime/scheduler.py` | 发言与动作的调度器。 |
| `ui/console.py` | 控制台 UI 展示，基于观察者更新。 |
| `config/settings.py` | 全局配置项，集中管理参数。 |
| `policies/` | YAML 格式的策略配置。 |
| `policies/intent_constraint.yaml` | 意向约束策略。 |
| `policies/intent_evaluation.yaml` | 意向评估策略。 |
| `policies/intent_proposal.yaml` | 意向生成策略。 |
| `policies/intent_attribution.yaml` | 贡献归因策略草案。 |
| `test/` | 简单的回归/单元测试样例。 |
| `test/test4agent_observe.py` | Agent 观察与可见性测试。 |
| `test/test4world.py` | 世界状态与事件传播测试。 |
| `test/test4demo1_without_llm.py` | 无 LLM 的端到端 demo 测试。 |
| `legacy/` | 早期版本的控制器与解释器保留代码。 |
| `zProposal/` | 设计提案与路线文档。 |
| `zProposal/demo之后的计划.txt` | v0.3 闭环计划：引入 proposer、统一事件出口。 |
| `zProposal/埋下的坑.txt` | 风险提示与节流、去重、预算等未来工作。 |
| `zProposal/简略版任务书.txt` | 项目概述、目标与技术路线。 |
| `zProposal/一些展望.docx` | 后续展望（DOCX）。 |
| `zProposal/第一阶段任务书.docx` | 第一阶段任务书（DOCX）。 |

## 项目理念与核心概念

- **事件优先**：一切外显行为都以 `Event` 记录，强调可见性与可追溯性，引用（`references`）串联协作脉络。
- **意向入队**：Agent 不直接发事件，而是提交 `Intention`，由解释器与路由裁决后进入世界，确保“先纪律，后智能”。【F:zProposal/demo之后的计划.txt†L10-L41】
- **克制的 Agent**：Agent 只声明行为，不解释历史，避免隐式耦合；引用的权重与完成状态留待后续归因与计算处理。【F:agents/agent.py†L12-L86】
- **可插拔策略**：通过 `policies/` 与 `agents/policies.py` 保持约束与评价的可配置性，为节流、去重、预算等机制预留空间。【F:zProposal/埋下的坑.txt†L1-L28】

## 工作流速览（v0.3 目标）

1. **事件触发**：外部或种子事件被世界看见。
2. **意向提案**：`agents/proposer.py` 根据触发事件生成 `Intention`（可先用规则，后接入 LLM）。
3. **排队与裁决**：`agents/controller.py` 将意向入队，`agents/interpreter.py` 结合策略进行裁决、补全或拒绝。
4. **路由与广播**：`platform/router.py` 作为唯一事件出口写入事件，`platform/world.py` 负责广播到可见域。
5. **观测与界面**：`ui/console.py` 等观察者实时展示事件流。

该闭环对应 zProposal 中的“最小闭环”任务：Event → Proposer → Interpreter → Router → World。后续会在 proposer 前加入上下文检索，给 LLM 提供“最近 N 条”参考以提升生成质量。【F:zProposal/demo之后的计划.txt†L1-L41】

## 设计思路摘录

- **防刷屏策略**：当前默认对普通 `speak` 不提议，优先处理 `request_anyone/request_specific` 等明确需要回应的事件，待节流/去重/预算后再放开。【F:zProposal/埋下的坑.txt†L1-L28】
- **可解释的贡献归因**：事件图将支撑未来的贡献度计算与可视化，结合 `policies/intent_attribution.yaml` 与 zProposal 的“多维度评估”愿景。【F:zProposal/简略版任务书.txt†L1-L33】
- **松耦合架构**：LLM、策略、存储均可替换；`llm/client.py` 提供降级策略，`events/store.py`/`query.py` 抽象存储与查询，为后续引入向量检索留接口。

## 使用建议

1. 创建/配置 `config/settings.py` 中的必要参数（LLM Key、调度频率等）。
2. 在 `main.py` 中注册所需 Agent、策略与观察者，随后启动事件循环。
3. 运行测试或示例：
   ```bash
   python -m test.test4demo1_without_llm
   ```
   或按需扩展更多脚本。

## 路线图（摘自 zProposal）

- **v0.3**：补齐 proposer，确保“意向入队”成为唯一动力，跑通最小闭环。【F:zProposal/demo之后的计划.txt†L1-L41】
- **v0.31/0.32**：加入节流（cooldown）、去重（dedupe）、预算（budget）、优先级（priority），防止 speak 链刷屏。【F:zProposal/埋下的坑.txt†L1-L28】
- **v0.4**：LLM 驱动的 proposer，结合事件查询提供上下文记忆；引入基础贡献度评估。 
- **更远期**：图算法驱动的贡献归因、可视化报告，以及与向量库/图数据库的结合，形成科研与工程并重的多 Agent 协作平台。【F:zProposal/简略版任务书.txt†L1-L33】

## 贡献

欢迎通过 Issue/PR 讨论设计或提交实现，尤其是围绕 proposer 细化、策略完善、事件图算法与可视化的贡献。提交代码前请结合策略文件与 zProposal 的路线思考整体一致性。