# 05 DeepSeek 接入与本地上下文策略

> 更新日期：2026-03-11

## 1. 对齐官方能力（DeepSeek）

按 DeepSeek 官方文档与 LangChain 官方集成建议：

- API 入口：`/chat/completions`。
- DeepSeek Chat API 为无状态调用：每次请求由客户端显式携带对话历史。
- Context Caching 由服务端自动处理前缀命中；调用侧不应依赖“隐式会话记忆”。
- LangChain 集成优先 `langchain-deepseek`，并保留 OpenAI 兼容回退路径（`langchain-openai + base_url`）。

## 2. 代码接入点（低耦合）

- 统一入口：`src/graphchat/infrastructure/llm/model_provider.py`
- 业务节点不直接触达供应商 SDK：`application/nodes/*` 仅调用 `model_provider.plan_action(...)`

环境变量：

- `GRAPHCHAT_MODEL`：如 `deepseek-chat`
- `GRAPHCHAT_MODEL_PROVIDER`：设为 `deepseek`
- `GRAPHCHAT_DEEPSEEK_API_KEY`：DeepSeek API Key
- `GRAPHCHAT_DEEPSEEK_BASE_URL`：默认 `https://api.deepseek.com`

注意：

- `.env.local` 为本地配置容器，运行前需将其变量导入进程环境。

## 3. 本地上下文边界（必须）

本项目上下文分层保持本地持久化：

- 事实层：`events.jsonl`（EventStore）
- 执行层：checkpointer（world/agent 独立 thread）
- 归纳层：`board.json`（BoardStore）

发往模型的上下文采用“受控窗口”：

- `last_event`
- 最近可见事件窗口（当前实现默认最近 5 条）

约束：

- 不将全量历史直接灌入模型上下文。
- 不把供应商会话当作事实源；事实仍以本地 EventStore 为准。

## 4. 运行与验收

## 4.1 本地运行前准备

1. 安装依赖（含 `langchain-deepseek` / `langchain-openai`）。
2. 在 `_GraphChat/.env.local` 填写 API Key。
3. 启动 CLI 或 demo 执行回归。

## 4.2 验收标准

- 配置正确时，`plan_action` 走结构化输出路径。
- 依赖缺失或配置错误时，自动回退规则模型且不中断主流程。
- 回归测试覆盖 DeepSeek 配置路径和回退路径。
