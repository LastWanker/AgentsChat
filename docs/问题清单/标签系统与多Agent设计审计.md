# 标签系统与多Agent设计审计（2026-03-09）

## 1. 结论速览

- 你说的“标签是类 RAG 系统”是成立的：当前是 `tags -> event_ids` 的索引召回，不是语义检索。
- 你说的“低效、错乱、不可控”也基本成立：标签生产和补全高度依赖 LLM，约束弱，漂移大。
- “Agent 经常忘了自己是谁”有架构根因：现在不是每个 Agent 独立会话上下文，只是每轮临时拼 Prompt。
- 当前项目“能跑、能玩海龟汤”，但离“经典多 AI 协作系统（状态机明确、动作空间受限、可验证）”还有明显差距。
- 当前 `langgraph` 接入是“外层包裹 legacy step”，不是“图驱动行为本体”。

---

## 2. 现状证据（按你关心点）

### 2.1 标签系统确实是类 RAG，但检索能力偏弱

- 标签索引核心是 `TagPool`：`src/events/session_memory.py`
  - 数据结构是 `tag -> {event_ids, hit_count}`。
- 召回入口：`src/events/reference_resolver.py`
  - 只按 `draft.retrieval_tags` 在 tag pool 取 `event_ids`，再转引用。
- 标签生成：`src/events/tagging.py`
  - 词法规则 + LLM 生成/补全混用，缺少稳定的领域词表和约束层。
- 提案阶段选标签：`src/agents/proposer.py`
  - 主要是文本包含匹配 + fallback 规则，语义排序缺失。

结论：这是“标签倒排索引式 RAG-like”，不是语义记忆系统，也不是可解释的检索策略系统。

### 2.2 Agent 是否有“独立上下文”？

短答：**不完全有**。

- LLM 客户端是无状态请求：`src/llm/client.py`。
- 每轮由 controller 现拼 context：`src/agents/controller.py::_build_context`。
- Prompt 里通过“你是 xxx”做身份提醒：`src/llm/prompts.py::build_intention_prompt`。
- Agent 本地 memory 主要是“看过哪些 event_id”：`src/agents/agent.py`。

结论：有“角色字段注入”，但没有“每 Agent 独立对话线程 + 独立短中长期记忆策略”。这正是“忘记自己是谁”的常见原因。

### 2.3 Schema 与命名存在漂移/冗余

- `IntentionDraft` 同时承载业务字段和大量运行态字段：`src/events/intention_schemas.py`。
- Finalizer 有多层 normalize 与兜底修正：`src/events/intention_finalizer.py`。
- JSON 解析策略宽松（截取大括号再解析）：`src/llm/schemas.py::_extract_json`。

结论：系统依赖“后处理修复”而不是“前置约束保证”，导致 schema 与意图长期不一致。

### 2.4 耦合与分层问题仍重

- `SessionMemory` 是 948 行“超级类”：`src/events/session_memory.py`
  - 同时做 personal task、tags、team board、异步维护、摘要、引用修复。
- `agents_chat` 新目录仍大量转发旧模块：
  - 例如 `src/agents_chat/application/*` 多处 `from agents...` / `from events...`。

结论：看似新结构，实则“双轨并存 + 旧内核复用”，改造可控性不足。

### 2.5 LangGraph 现状与预期有落差

- `src/agents_chat/workflow/langgraph_engine.py` 的 `_tick_node` 直接调用 `self._legacy.step()`。
- 图状态主要是 `tick/max_ticks/done`，不是业务主状态（如草稿/终稿/路由决策状态机）。

结论：现在更像“LangGraph 外壳”，还不是“LangGraph 驱动的行为边界系统”。

### 2.6 隐蔽但严重的问题：文本编码污染（Mojibake）

- 多文件出现明显乱码文本（如 `浣犳槸...`）：`src/llm/prompts.py`、`src/llm/schemas.py`、`src/agents/*.py`、`src/events/session_memory.py` 等。

结论：这会直接劣化 Prompt 语义，造成 LLM 行为飘逸和“不按 schema 输出”。

---

## 3. 与主流多 Agent 协作系统的差距

主流形态通常是：

1. 图/状态机先定义动作空间（不是让模型任意发挥）。
2. 记忆分层明确（短期会话、长期事实、检索索引分离）。
3. 工具/技能注册与 Agent 身份解耦。
4. Schema 强约束（结构化输出失败可重试或降级到固定动作）。
5. 可观测与评估优先（节点级指标、失败归因）。

当前项目最大差距：

- 行为边界仍靠 prompt 文案，而不是图状态+路由硬约束。
- 标签系统承担了过多“语义理解”职责，但缺少稳定策略层。
- 技能/能力模型尚未抽象成统一 action/tool contract。

---

## 4. 问题分级（建议先打掉 P0）

### P0（不解决就会持续“看起来随机”）

1. 编码乱码污染 Prompt 与文案。
2. 无每 Agent 独立上下文线程（身份漂移高发）。
3. 标签体系无受控词表/命名空间，LLM 自由生成导致漂移。
4. LangGraph 未真正接管业务状态流转（仅包壳）。

### P1（解决后系统才会“可维护”）

1. `SessionMemory` 超级类拆分不足。
2. Schema 冗余与 normalize 过多，边界不清。
3. 新旧模块双轨并存，命名与导入路径不一致。
4. 引用 weight 语义长期默认值化，实际价值有限。

### P2（中期优化）

1. 维度命名统一（confidence/motivation/urgency 与 weight 三维语义说明）。
2. 测试聚焦从“能跑”升级到“行为一致性与漂移监控”。

---

## 5. 如何靠近主流（且兼容你已有改造主线）

### 5.1 先做“可控化”，再做“智能化”

顺序建议：

1. 先修编码与契约：清理乱码、收紧 schema、固定失败重试策略。
2. 再做上下文隔离：每 Agent 独立 `thread_id` / memory scope。
3. 再做标签重构：受控词表 + 命名空间 + 检索排序，减少自由生成。
4. 最后让 LangGraph 真正接管节点状态与路由。

### 5.2 标签系统改造方向（重点）

- 从“LLM 生成 tag”改成“受控标签选择 + 小范围补全”。
- 标签改为分层：
  - `topic/*` 主题
  - `task/*` 任务
  - `role/*` 角色
  - `session/*` 会话态
- 召回改为多信号打分：
  - 标签命中
  - 时间衰减
  - 引用链距离
  - 发送者/角色相关性

### 5.3 Agent 身份稳定化方向

- 每个 Agent 独立对话线程（至少逻辑线程）。
- System Prompt 固定化 + 禁止动态拼接关键身份条款。
- 将“我是谁/我能做什么”从自然语言迁到结构化 `AgentProfile`。

### 5.4 LangGraph 落地方向

- 让图节点直接承载业务动作：
  - `observe -> retrieve_memory -> propose_action -> validate_schema -> finalize -> emit`
- 路由只允许有限动作集合（例如 `speak/ask/defer/escalate`）。
- 把“投票/分组/函数调用”变成显式节点，不再靠模型自发决定是否调用。

---

## 6. 是否应重开一个“原汁原味 LangGraph”项目？

建议是：**先做 2-3 周可控化冲刺，再决定是否重开。**

建议重开的触发条件：

1. P0 处理后，输出漂移仍高且不可归因。
2. 旧模块兼容层导致 30% 以上开发时间浪费在“转发/修补”。
3. 无法在图中表达核心业务状态（被 legacy 绑定）。

如果以上 2 条及以上成立，重开仓更经济；否则可继续渐进重构。

---

## 7. 一句话评估

这是一个“能跑、但设计债明显、且正处在可重构窗口期”的系统；如果要做经典多 AI 协作，核心不是继续加 prompt，而是把行为严格收敛到图状态与受控动作空间里。
