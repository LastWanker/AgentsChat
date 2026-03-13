# 图可视化说明

本目录由导出脚本生成：
- `graph_bundle.json`：图数据包（当前版本 `1.1.0`）。
- `graph_viewer.html`：离线查看器（支持子图弹层、节点悬浮、transition 面板）。

## 如何更新
在项目根目录执行：

```powershell
python _GraphChat/scripts/export_graph_viewer.py --no-open
```

默认产物：
- `_GraphChat/docs/graphs/graph_bundle.json`
- `_GraphChat/docs/graphs/graph_viewer.html`

## 查看方式
优先使用本地 HTTP 服务打开，避免 `file://` 模块加载限制：

```powershell
python _GraphChat/scripts/serve_graph_viewer.py
```

访问：

```text
http://127.0.0.1:8765/graph_viewer.html
```

## 新增能力（M5）
1. 侧栏展示 transition 列表，区分：
   - `edge`
   - `conditional`
   - `send`
   - `loop`
2. transition 会标记 `rendered`：
   - `true`：Mermaid 图中已显示
   - `false`：多见于动态路由/Send，Mermaid 未直接展开，但语义在元数据中可见

## 新增能力（M8）
1. Agent 主图显式拆分“计划”和“执行”：
   - `plan_action -> action_parallel_subgraph(plan) -> skill_execution_subgraph(execute) -> lifecycle_gate`
2. 新增 `skill_execution_subgraph` 子图，包含离散 skill lane 节点：
   - `skill_rag` / `skill_board` / `skill_governance` / `skill_dialog` / `skill_generic`
3. skill lane 由 `Send` 并行分发，不是固定串行链，执行完成后汇聚并输出 `plan_execution_report`。

## 新增能力（M9）
1. `graph_viewer.html` 增加中英界面切换，默认中文。
2. 语言选择会保存到本地（`localStorage`），下次打开自动沿用。

## Bundle 协议（简化）
```json
{
  "version": "1.1.0",
  "root_graph_id": "agent",
  "graphs": {
    "<graph_id>": {
      "title": "...",
      "description": "...",
      "mermaid": "...",
      "nodes": { "...": { "title": "...", "subgraph_id": "..." } },
      "transitions": [
        {
          "source": "A",
          "target": "B",
          "type": "send|conditional|loop|edge",
          "note": "...",
          "rendered": false
        }
      ]
    }
  }
}
```
