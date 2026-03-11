# 图可视化（通用方案）

本目录由导出脚本生成，核心目标是低耦合、可复用：

- `graph_bundle.json`：图数据包（通用协议）。
- `graph_viewer.html`：通用查看器（支持悬停信息、子图毛玻璃弹层）。

## 1. 如何更新可视化

在项目根目录执行：

```powershell
python _GraphChat/scripts/export_graph_viewer.py
```

说明：

- 该脚本会导出 `bundle/html`，并默认自动打开本地 `file://` 页面。
- 若浏览器因本地模块加载策略导致空白，使用下面的 `serve_graph_viewer.py`。

推荐直接启动本地服务（避免 `file://` 模块加载限制）：

```powershell
python _GraphChat/scripts/serve_graph_viewer.py
```

然后访问：

```text
http://127.0.0.1:8765/graph_viewer.html
```

说明：

- 该脚本会先导出，再启动本地 HTTP 服务，并默认自动弹出浏览器。
- 若 `8765` 端口被占用或权限受限（例如 WinError 10013/10048），脚本会自动尝试后续端口。
- 可用 `--no-open` 关闭自动弹出。

默认输出到：

- `_GraphChat/docs/graphs/graph_bundle.json`
- `_GraphChat/docs/graphs/graph_viewer.html`

## 2. 交互说明

- 悬停节点：显示状态说明、关键字段、来源文件。
- 点击“有子图”的节点：暗色毛玻璃层覆盖母图，弹出子图。
- 侧栏可切换 world/agent/子图。

## 3. 通用协议（可迁移到其他项目）

`graph_bundle.json` 结构（简化）：

```json
{
  "version": "1.0.0",
  "root_graph_id": "agent",
  "graphs": {
    "<graph_id>": {
      "title": "...",
      "description": "...",
      "mermaid": "...",
      "nodes": {
        "<node_id>": {
          "title": "...",
          "description": "...",
          "source_file": "...",
          "state_fields": ["..."],
          "subgraph_id": "..."
        }
      }
    }
  }
}
```

只要其他项目能产出相同协议，就能直接复用 `graph_viewer.html`。

## 4. 当前限制

- 节点匹配依赖 Mermaid 渲染标签文本，后续可升级为显式 data-id 映射。
- 浏览器打开本地 HTML 时需要联网加载 Mermaid CDN（后续可改为本地静态资源）。
