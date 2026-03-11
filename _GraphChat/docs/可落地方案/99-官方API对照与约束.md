# 99 官方 API 对照与约束

> 校验日期：2026-03-10

## 1. LangGraph 官方能力对照

- 图构建：`StateGraph(...)`、`add_node(...)`、`add_edge(...)`、`add_conditional_edges(...)`
- 图编译：`compile(checkpointer=...)`
- 动态分发：`Send(...)`
- 节点命令：`Command(goto=..., update=..., resume=...)`
- 人工中断：`interrupt(payload)`
- 流式运行：`stream(...) / astream(...)`
- 子图：官方 `use-subgraphs`

本项目约束：禁止自定义一套“伪图调度器”替代以上能力。

## 2. LangChain 官方能力对照

- 模型抽象：统一使用 LangChain chat model 接口
- 工具抽象：使用标准 tool 机制封装外部能力
- 检索抽象：retriever/vector store 通过 LangChain 适配层接入

本项目约束：节点内模型调用与工具调用必须走 LangChain 抽象，不直接把供应商 SDK 分散到业务节点。

## 3. 官方文档入口（主引用）

- LangGraph Overview  
  https://docs.langchain.com/oss/python/langgraph/overview
- Graph API  
  https://docs.langchain.com/oss/python/langgraph/graph-api
- Persistence  
  https://docs.langchain.com/oss/python/langgraph/persistence
- Streaming  
  https://docs.langchain.com/oss/python/langgraph/streaming
- Subgraphs  
  https://docs.langchain.com/oss/python/langgraph/use-subgraphs
- Interrupts  
  https://docs.langchain.com/oss/python/langgraph/interrupts
- LangChain Agents  
  https://docs.langchain.com/oss/python/langchain/agents

## 4. 代码评审检查项（与官方一致性）

- 是否使用 `StateGraph` 正式建图，而非手写 while-loop 编排
- 是否通过 `Command/Send/interrupt` 实现跳转、并发和中断
- 是否所有可恢复流程都配置了 `checkpointer`
- 是否子图采用官方模式挂载，而非手工 if/else 拆分
- 是否节点内部模型/工具调用经过 LangChain 抽象层

