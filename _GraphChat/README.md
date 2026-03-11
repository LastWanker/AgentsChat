# _GraphChat

最小可运行骨架，基于 LangGraph/LangChain 官方模式构建。

## 快速运行

```powershell
python _GraphChat/run_demo.py
```

或：

```powershell
$env:PYTHONPATH = "_GraphChat/src"
python -m graphchat --session demo --text "大家先检索信息再投票"
```

## DeepSeek 配置（本地）

推荐在 `_GraphChat/.env.local` 中配置：

```dotenv
GRAPHCHAT_MODEL=deepseek-chat
GRAPHCHAT_MODEL_PROVIDER=deepseek
GRAPHCHAT_DEEPSEEK_API_KEY=sk-xxxx
GRAPHCHAT_DEEPSEEK_BASE_URL=https://api.deepseek.com
```

说明：

- 模型层优先走 `langchain-deepseek`，不可用时回退 OpenAI 兼容 (`langchain-openai`)。
- 若未配置或依赖缺失，会自动回退 `RuleBasedModelProvider`，保证运行不阻塞。
- 上下文本地化策略保持不变：事件/任务板/checkpoint 在本地持久化，模型调用仅发送受控窗口。
- `.env.local` 仅作为本地配置文件；运行前需把其中环境变量导入当前 shell。

## 运行时能力（当前）

- 检索：`world_history + ask_peer + file_search + web_search` 多通道，可开关，通道失败不阻塞主流程。
- 路由：支持 `group_registry/dm_registry` 精细可见性路由。
- 审批：支持 `interrupt -> 审批队列 -> resume` 服务化闭环。
- 流式：`stream_user_text(...)` 输出节点更新流与消息流。
- 生命周期：`AgentRegistry` 支持动态新增/启停 Agent，不改主图结构。
