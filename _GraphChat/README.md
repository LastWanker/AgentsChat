# _GraphChat（主项目）

`_GraphChat` 是本仓库的主项目与默认入口。

根目录 `AgentsChat` 仅作为实验外壳与历史过渡区，不代表主线实现。

## 快速运行

```powershell
python _GraphChat/run_demo.py
```

或：

```powershell
$env:PYTHONPATH = "_GraphChat/src"
python -m graphchat --session demo --text "大家先检索信息再投票"
```

## 本地模型配置示例（DeepSeek）

在 `_GraphChat/.env.local` 配置：

```dotenv
GRAPHCHAT_MODEL=deepseek-chat
GRAPHCHAT_MODEL_PROVIDER=deepseek
GRAPHCHAT_DEEPSEEK_API_KEY=sk-xxxx
GRAPHCHAT_DEEPSEEK_BASE_URL=https://api.deepseek.com
```

## 目录说明

- `src/graphchat/`：核心代码
- `scripts/`：运行和调试脚本
- `tests/`：单元与集成测试
- `docs/`：仅保留必要 README，其他文档默认本地保存
