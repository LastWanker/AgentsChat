# _GraphChat 内部 APP 使用手册（非开发者）

> 适用对象：被交付代码包、但不参与开发的人。  
> 目标：只看这份文档就能把 APP 跑起来并完成日常操作。

## 1. 这套 APP 的“本体”是什么？

不是一个独立安装包客户端，而是两部分组成：

1. API 服务（后端本体）  
   - 负责运行多 Agent 状态机、处理消息、审批、世界命令、可观测数据。
2. 内部控制台页面（前端操作面板）  
   - 通过浏览器访问，用来操作 API。

对应文件：

- 服务启动脚本：`_GraphChat/scripts/run_api_server.py`
- 控制台打开脚本：`_GraphChat/scripts/run_internal_console.py`
- 控制台页面：`_GraphChat/src/graphchat/interfaces/ui/internal_console.html`

## 2. internal-console 是唯一页面吗？

不是。

你主要会用两个页面：

1. `internal-console`（主操作页面，日常使用就靠它）  
   - 地址：`http://127.0.0.1:8000/internal-console`
2. `graph_viewer`（图结构观察页面，偏技术/排障）  
   - 地址：`http://127.0.0.1:8765/graph_viewer.html`（需要单独起静态服务）

建议：非开发者只用 `internal-console` 就够了。

## 3. 5 分钟启动（Windows）

在仓库根目录执行：

```powershell
python _GraphChat/scripts/run_api_server.py --host 127.0.0.1 --port 8000 --api-token your-token
```

保持上面窗口不要关。再开一个新窗口执行：

```powershell
python _GraphChat/scripts/run_internal_console.py
```

浏览器会打开控制台。  
如果没自动打开，手动访问：`http://127.0.0.1:8000/internal-console`

## 4. 控制台怎么用（按面板）

默认界面语言是中文，可切换英文。

## 4.1 Connection（连接设置）

要填的关键项：

- `API 基础地址`：本机默认留空即可（同源访问）
- `API Token`：填你启动服务时的 `--api-token`
- `会话 ID`：建议一个业务会话一个 ID（例如 `team_sync_001`）
- `World Scope`：默认 `group:main`

先点“检查健康状态”，确认服务可用。

## 4.2 Messaging（消息交互）

- “发送消息”：同步返回本轮结果
- “流式消息（SSE）”：实时看到节点更新和消息事件
- “加载事件（轮询回退）”：SSE 不稳定时使用

## 4.3 World Commands（世界命令）

这是控制系统行为的核心入口，可执行创建 Agent、建组、注入任务等。

示例：新建一个 Agent（`agent_9`）

```json
[
  {
    "type": "create_agent",
    "payload": {
      "agent_id": "agent_9",
      "enabled": true
    }
  }
]
```

示例：把 `agent_9` 放到一个组

```json
[
  {
    "type": "upsert_group",
    "payload": {
      "group_id": "team_ops",
      "members": ["agent_1", "agent_9"]
    }
  }
]
```

示例：给 Agent 配置检索通道

```json
[
  {
    "type": "set_agent_retrieval",
    "payload": {
      "agent_id": "agent_9",
      "channels": ["web_search", "world_history"]
    }
  }
]
```

## 4.4 Approvals（审批）

如果某个动作触发审批，会出现在审批面板。

- “通过”：继续执行后续流程
- “拒绝”：终止/回退该审批动作

## 4.5 Direct Chat（直聊）

直接和指定 Agent 对话：

- `Agent ID` 填目标（例如 `agent_1`）
- 输入文本后点“发送直聊”

## 4.6 Observability（可观测）

点“刷新可观测快照”可看到：

- `agents`：Agent 注册信息（是否启用等）
- `last_agent_status`：每个 Agent 最近状态（运行/审批等待/完成）
- `pending_approval_count`：待审批数量
- `skill_guard_profiles`：动作 guard 配置快照

## 5. 我怎么判断 Agent 当前状态？

看两处：

1. 控制台 `Observability` 面板  
   - 首选 `last_agent_status`
2. 控制台 `Messaging`/`Events` 日志  
   - 看每轮是否持续产出事件

## 6. 数据和日志在哪里？

- 会话/事件数据：`_GraphChat/data/`
- 服务日志：`_GraphChat/logs/graphchat_api.log`

## 7. 常见问题

## 7.1 页面打不开

先检查服务是否启动：

- `http://127.0.0.1:8000/healthz` 返回 `status=ok`

## 7.2 提示 401 unauthorized

说明 token 不一致。  
控制台里的 `API Token` 必须和启动参数 `--api-token` 完全一致。

## 7.3 看不到流式输出

用“加载事件（轮询回退）”按钮。  
某些内网代理对 SSE 支持不好，这是预期回退路径。

## 7.4 新建 Agent 后没有响应

依次检查：

1. 是否 `enabled=true`
2. 是否在目标 group 里（`upsert_group`）
3. 会话消息的 `World Scope` 是否命中该 group

## 8. 推荐日常操作顺序

1. 启动 API 服务  
2. 打开 internal-console  
3. 健康检查  
4. 创建/调整 Agent 与 group  
5. 发消息或注入任务  
6. 有审批就处理审批  
7. 用 observability 看状态与效果
