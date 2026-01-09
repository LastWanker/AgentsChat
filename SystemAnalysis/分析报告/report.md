# AgentsChat 体检报告（v0.1）
> 体检对象：事件驱动多智能体实验场  
> 体检结论：底子不差，脑子还在“试运行”，跑起来没问题，但要变强还得长肉、练心肺。

## 证据来源与命令记录（可追溯）
**我用到的终端命令（用于阅读/确认结构与文件内容）：**
- `ls`（确认顶层目录结构；与结构文档一致）。
- `find .. -name AGENTS.md -print`（检查是否存在额外指令文件；结构文档未列出 AGENTS.md）。
- `sed -n '1,200p' README.md`（查看项目概览与核心流程说明）。
- `sed -n '1,200p' 文件结构.md`（确认模块划分与目录分工）。
- `sed -n '1,200p' main.py`（确认启动入口与默认配置）。
- `sed -n '1,200p' runtime/bootstrap.py`（确认运行时装配逻辑）。
- `sed -n '1,200p' runtime/loop.py`（确认主循环与意向处理）。
- `sed -n '1,200p' agents/proposer.py`（确认规则/LLM 提案器行为）。
- `sed -n '1,200p' agents/interpreter.py`（确认策略解释器与安全求值）。
- `sed -n '1,200p' platform/router.py`（确认路由/节流与事件落盘）。
- `sed -n '1,200p' llm/client.py`（确认 LLM 客户端与重试）。
- `sed -n '1,200p' llm/prompts.py`（确认 LLM prompt 约束）。
- `sed -n '1,200p' llm/schemas.py`（确认 LLM 输出 schema）。
- `sed -n '1,200p' events/intention_schemas.py`（确认意向 draft/final 结构）。
- `sed -n '1,200p' events/intention_finalizer.py`（确认两段式 finalize）。
- `sed -n '1,200p' policies/intent_constraint.yaml`（确认策略约束规则）。
- `sed -n '1,200p' ui/live_ui.py`（确认 Live UI 的实现形态）。
- `sed -n '1,200p' config/settings.py`（确认 LLM/UI 配置入口）。
- `sed -n '1,200p' test/test_main_runtime_flow.py`（确认基础 E2E 测试）。
- `sed -n '1,200p' test/test4demo1_without_llm.py`（确认最小可运行 demo）。

---

## 0) 如何评价项目整体？
**一句话：**“闭环已经跑起来，结构清晰，但智能程度还在‘婴幼儿’阶段，离‘熟练工’还有一段练级。”
- 项目核心闭环“事件→意向→解释→路由→事件广播”已经成型，且在 README 中清晰阐述，运行时装配与主循环也有完整实现。
- 规则模式可无 LLM 运行，适合作为实验场的“安全底盘”。

---

## 1) 项目结构专业、正规、符合业界习惯吗？
**总体评价：是的，架构分层和目录划分很“业内”。**
- 目录按职责拆分：`agents/`、`platform/`、`events/`、`runtime/`、`llm/`、`ui/`、`policies/`、`test/`，这是比较典型的中大型 Python 系统分层方式。
- 入口 `main.py`、运行时装配 `runtime/bootstrap.py`、主循环 `runtime/loop.py` 的调用链清晰，符合“入口→装配→执行”惯例。

---

## 2) 项目有没有明显短板，会导致可能效果不好？
**有三个“效果瓶颈级”的短板：**

1) **智能生成层仍是“规则占位脑”**  
   - 提案器 `IntentionProposer` 的规则模式非常保守，主要是固定模板回复，实际生成质量有限。  
   - LLM 模式虽然有 prompt/schema，但仍可能在 JSON 解析失败时回退到规则模式，导致智能输出质量不稳定。

2) **LLM 路径“能走但容易绊”**  
   - LLM 配置与客户端已经具备（包括重试、流式等），但默认是关闭，需要外部环境变量驱动；且 prompt 要求严格 JSON 输出，对模型稳定性要求较高。  

3) **执行层缺少“目标感/任务导向”**  
   - 目前的两段式流程主要是基于 request/speak 的响应，没有更高层任务规划、目标分解或结果评估机制，容易导致对话空转或产出浅层化。

---

## 3) 哪些部分相对无用，或可考虑迭代剪枝？
**可能被剪枝或分流的“备份舱”：**

- `legacy/` 与 `zProposal/` 属于历史或设计阶段材料，若当前版本已稳定，建议迁移到文档仓库或归档，减少主项目噪音。
- `policies/intent_evaluation.yaml`、`intent_proposal.yaml`、`intent_attribution.yaml` 在 README 中被描述为“草案”，当前系统主要使用 `intent_constraint.yaml`，其余可先放在 “规划区” 以免误导使用者。

---

## 4) 项目有哪些互相矛盾的地方？
**目前没有硬性逻辑冲突，但有“命名语义不一致”的风险点：**

- **Event 的 payload/content 命名混用**：  
  - 提案器里读取 `payload` 或 `content`，prompt 里展示 `content`，路由器最终把 `Intention.payload` 转成 `Event.content`。这在扩展 UI、策略或日志时容易引起“字段到底叫啥”的混乱。

---

## 5) 哪些地方还很粗糙或忘记做了？
**主要是“配套设施”层面：**

- **测试覆盖面偏基础**：  
  - 有 demo 和最小闭环测试，但 LLM 流程、UI、策略边界等高级路径缺少覆盖。

- **UI 还属于“监控面板原型”**：  
  - Live UI 只是读取 events.jsonl 并简单展示，缺少交互式控制或可视化分析。

---

## 6) 针对 agent 的聪明和稳定，有什么提议？
**建议围绕“三件套”：更聪明、更稳、更可控。**

1) **更聪明：把“检索计划”升级为真实检索策略**  
   - 现在 `RetrievalInstruction` 已经具备结构（关键词、scope、thread_depth 等），但实际策略仍很基础；可把 `recent_events` 与 `referenced_events` 真正融入 LLM prompt 或规则决策中。

2) **更稳：加强 LLM 输出的验证与修复**  
   - 当前 parse 失败就回退规则，可能导致“忽然很笨”；可考虑加一层“轻量修复器”（比如自动补字段或重试），提升稳定性。

3) **更可控：用策略“软约束”指导行为**  
   - 目前策略集中于“硬性 forbid/require”，建议逐步加入“优先级、奖励或降级”机制，让 agent 行为更像“被训练过”而非“被拦截”。

---

## 7) 还有什么角度上的建议？
**给你三个“体检外科”的建议：**

1) **增加“可观察性”仪表盘**  
   - 现有 Live UI 已能读取 session 与 events，继续加上：意向->事件转化率、抑制原因统计、agent 互动热力图，会非常“科研味儿”。

2) **把“策略文件”变成实验参数，而非“静态配置”**  
   - 目前 YAML 规则是固定文件；若能在 runtime 中热更新或切换策略版本，会更利于实验迭代。

3) **补一份“贡献者指南”**  
   - 结构很清晰，但没有专门写给“新同学”的快速上手路线；建议加个 CONTRIBUTING 或简化版 Architecture Overview。项目气质更“专业开源”。

---

# 总结（TL;DR）
- 架构专业、闭环可跑、分层清晰，已经具备“实验场底座”。
- 最大短板是智能层仍以规则为主、LLM 输出稳定性一般、缺少更高层目标导向。建议优先强化 LLM 可靠性 + 检索策略。
- 剪枝方向：legacy 与 zProposal 可归档，草案策略文件可放“规划区”。
