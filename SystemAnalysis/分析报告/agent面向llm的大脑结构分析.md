# Agent 面向 LLM 的“大脑结构”分析
（SystemAnalysis/agent面向llm的大脑结构分析.md）

> 目标：把 Agent 在 LLM 加持下的“脑回路”讲清楚。  
> 包括：索引机制、起草机制、最终生成机制，以及它们的混合与交互。

---

## 1. 大脑结构总览：三段式协作
你可以把 Agent 的大脑想成三个“脑区”：

1. **索引区（检索/回忆）**：决定要回忆哪些事件。
2. **起草区（Draft）**：写个初稿，表达“我想说什么”。
3. **成文区（Final）**：补齐引用、打上权重，输出正式内容。

一句话：
> 先想该翻哪本书，再写草稿，最后写成“公开发言”。

---

## 2. 索引机制：从“想一想”到“查一查”

### 2.1 触发点
- 触发事件来自 World（新 Event）。
- Controller 把事件交给 Proposer。

### 2.2 RetrievalInstruction 的角色
- Draft 中的 `retrieval_plan` 是“我要查的资料清单”。
- 包含关键词、事件类型、scope、thread_depth 等字段。

### 2.3 当前问题
- retrieval_plan 结构完整，但策略偏基础。
- 实际检索更多靠“近邻事件”与“引用链”。

通俗解释：
> 这就像图书馆已经有目录卡，但你还只翻第一页。

---

## 3. 起草机制：Draft 阶段

### 3.1 Draft 产生逻辑
- Proposer 根据 trigger_event 生成 Draft。
- 在规则模式下，主要是固定模板（submit / speak）。
- 在 LLM 模式下，调用 prompt + schema。

### 3.2 Draft 的价值
- Draft 是一种“可排队的意向草稿”。
- 它不含真实引用，只告诉系统“我要什么证据”。

### 3.3 Draft 的风险点
- LLM 输出不稳定会直接回退规则模式。
- 过度模板化可能导致内容单调。

---

## 4. 成文机制：Final 阶段

### 4.1 Finalizer 的作用
- Draft 只是草稿。
- Finalizer 会根据 retrieval_plan 解析引用，补齐 references。

### 4.2 引用选取逻辑
- 通过 ReferenceResolver 根据检索计划抓事件。
- 再由 LLM 或默认权重生成 weight。

### 4.3 当前争议点
- LLM 生成 weight 容易幻觉。
- 没有评估模块时，权重质量不稳定。

通俗比喻：
> Finalizer 像编辑部，负责查资料、补引用、标注权重，然后盖章发布。

---

## 5. 三者混合：脑区协作关系

### 5.1 正常流程
```
World 事件
  ↓
索引（retrieval_plan）
  ↓
Draft 生成（起草）
  ↓
Finalizer（补引用+权重）
  ↓
Interpreter 审核
  ↓
Router 广播
```

### 5.2 关键连接点
- **索引 ↔ 起草**：Draft 里包含 retrieval_plan。
- **起草 ↔ 成文**：Finalizer 依赖 Draft 的“检索计划”。
- **成文 ↔ 审核**：Interpreter 决定是否允许最终意向。

一句话：
> 这是一个“先找资料→写草稿→审核出版”的流水线。

---

## 6. reference 选取逻辑分析

### 当前逻辑（简化版）
1. Draft 里写好 retrieval_plan。
2. ReferenceResolver 根据 plan 抓取事件。
3. Finalizer 把候选引用套上 weight。

### 可能的问题
- 如果 retrieval_plan 太模糊，引用就会“偏题”。
- 如果 weight 由 LLM 直接给，会出现“主观瞎评”。

---

## 7. 如何改进？（更聪明、更稳）

1) **索引更聪明**
- 用关键词 + embedding 检索，而不是只靠时间顺序。
- 建立“主题记忆池”。

2) **Draft 更丰富**
- 允许 Draft 生成多版本，再做排序筛选。

3) **Final 更可信**
- 引入独立评估器计算 weight。
- 或者采用规则+LLM混合评分。

---

## 8. 结论（通俗版）
- 现在的大脑结构就像“刚装好三件套的机器人”。
- 有记忆、有草稿、有最终发布，但三者配合还不够聪明。
- 最关键的短板：索引机制太弱、权重生成太主观。

一句话总结：
> 大脑结构已经有框架，但还缺“联想力”和“校对员”。

