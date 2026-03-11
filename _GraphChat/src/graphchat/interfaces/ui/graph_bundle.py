from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


NODE_DECL_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(")


@dataclass
class GraphEntry:
    graph_id: str
    title: str
    description: str
    mermaid: str
    nodes: dict[str, dict[str, Any]]


def _extract_node_ids(mermaid_text: str) -> list[str]:
    node_ids: list[str] = []
    for line in mermaid_text.splitlines():
        m = NODE_DECL_RE.match(line.strip().replace("\t", ""))
        if not m:
            continue
        node_id = m.group(1)
        if node_id not in node_ids:
            node_ids.append(node_id)
    return node_ids


def build_graph_entry(
    graph_id: str,
    compiled_graph,
    graph_meta: dict | None = None,
) -> GraphEntry:
    mermaid = compiled_graph.get_graph().draw_mermaid()
    node_ids = _extract_node_ids(mermaid)
    graph_meta = graph_meta or {}
    node_meta_map: dict[str, dict[str, Any]] = graph_meta.get("nodes", {})

    nodes: dict[str, dict[str, Any]] = {}
    for node_id in node_ids:
        base = {
            "node_id": node_id,
            "title": node_id,
            "description": "待补充节点说明",
            "source_file": "",
            "state_fields": [],
        }
        base.update(node_meta_map.get(node_id, {}))
        nodes[node_id] = base

    return GraphEntry(
        graph_id=graph_id,
        title=graph_meta.get("title", graph_id),
        description=graph_meta.get("description", ""),
        mermaid=mermaid,
        nodes=nodes,
    )


def build_graph_bundle(graph_entries: list[GraphEntry], root_graph_id: str) -> dict[str, Any]:
    return {
        "version": "1.0.0",
        "root_graph_id": root_graph_id,
        "graphs": {entry.graph_id: {
            "graph_id": entry.graph_id,
            "title": entry.title,
            "description": entry.description,
            "mermaid": entry.mermaid,
            "nodes": entry.nodes,
        } for entry in graph_entries},
    }


def write_graph_bundle(bundle: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "graph_bundle.json"
    out_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def write_bundle_html(bundle: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / "graph_viewer.html"
    bundle_json = json.dumps(bundle, ensure_ascii=False)
    html_template = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Graph Viewer</title>
  <style>
    :root {{
      --bg: #0f1117;
      --panel: rgba(12, 16, 26, 0.88);
      --text: #e8edf5;
      --muted: #9eb0c8;
      --accent: #8ddcff;
      --accent-strong: #c6f0ff;
      --glass: rgba(10, 12, 20, 0.66);
      --border: rgba(170, 228, 255, 0.42);
      --control-bg: rgba(8, 12, 20, 0.94);
      --card-bg: rgba(10, 15, 24, 0.8);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Microsoft YaHei UI", "Noto Sans SC", sans-serif;
      background:
        radial-gradient(circle at 20% 15%, rgba(98,214,255,.18), transparent 38%),
        radial-gradient(circle at 80% 75%, rgba(74,255,166,.12), transparent 42%),
        linear-gradient(160deg, #0c0e14, #111726 70%);
      color: var(--text);
      min-height: 100vh;
    }}
    .app {{
      display: grid;
      grid-template-columns: 320px 1fr;
      min-height: 100vh;
      gap: 0;
    }}
    .side {{
      border-right: 1px solid var(--border);
      background: var(--panel);
      backdrop-filter: blur(8px);
      padding: 16px;
    }}
    .main {{
      position: relative;
      padding: 16px;
    }}
    h1 {{
      font-size: 18px;
      margin: 0 0 12px 0;
      letter-spacing: .4px;
    }}
    .hint {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
      margin-bottom: 12px;
    }}
    select, button {{
      width: 100%;
      border: 1px solid var(--border);
      background: var(--control-bg);
      color: var(--text);
      border-radius: 10px;
      padding: 8px 10px;
      margin-bottom: 10px;
    }}
    select option {{
      background: #0d1320;
      color: var(--text);
    }}
    .meta {{
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
      background: var(--card-bg);
      min-height: 160px;
      white-space: pre-wrap;
      font-size: 13px;
      line-height: 1.6;
      color: var(--muted);
    }}
    .graph-card {{
      border: 1px solid var(--border);
      border-radius: 16px;
      background: var(--card-bg);
      padding: 12px;
      overflow: auto;
      min-height: calc(100vh - 48px);
    }}
    #graphContainer svg {{
      max-width: 100%;
      height: auto;
    }}
    .tooltip {{
      position: fixed;
      z-index: 30;
      max-width: 360px;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: rgba(5, 8, 14, 0.9);
      color: var(--text);
      font-size: 12px;
      pointer-events: none;
      display: none;
      box-shadow: 0 10px 30px rgba(0,0,0,.35);
      white-space: pre-wrap;
      line-height: 1.5;
    }}
    .overlay {{
      position: fixed;
      inset: 0;
      display: none;
      z-index: 20;
      background: var(--glass);
      backdrop-filter: blur(9px);
      align-items: center;
      justify-content: center;
      padding: 28px;
    }}
    .overlay.show {{ display: flex; }}
    .overlay-panel {{
      width: min(1100px, 96vw);
      max-height: 90vh;
      overflow: auto;
      border-radius: 16px;
      border: 1px solid var(--border);
      background: rgba(8, 12, 20, 0.94);
      padding: 14px 14px 8px 14px;
      box-shadow: 0 20px 40px rgba(0,0,0,.35);
    }}
    .overlay-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;
    }}
    .overlay-title {{
      font-size: 16px;
      margin: 0;
    }}
    .close-btn {{
      width: auto;
      margin: 0;
      padding: 6px 10px;
      cursor: pointer;
    }}
    .node-subgraph-hint {{
      filter: drop-shadow(0 0 4px rgba(98,214,255,.45));
    }}
    #graphContainer g.node-subgraph-hint rect,
    #graphContainer g.node-subgraph-hint polygon,
    #overlayGraph g.node-subgraph-hint rect,
    #overlayGraph g.node-subgraph-hint polygon {{
      stroke: var(--accent-strong) !important;
      stroke-width: 1.6px !important;
      filter:
        drop-shadow(0 0 0 var(--accent-strong))
        drop-shadow(0 0 0 var(--accent-strong));
    }}
    #graphContainer g.node-subgraph-hint .label,
    #overlayGraph g.node-subgraph-hint .label {{
      font-weight: 700;
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside class="side">
      <h1>Graph 可视化</h1>
      <div class="hint">支持悬停节点看状态信息；点击带子图节点进入毛玻璃子图层。</div>
      <select id="graphSelect"></select>
      <button id="btnRoot">回到根图</button>
      <div id="graphMeta" class="meta">请选择图</div>
      <hr style="border-color: var(--border); border-style: solid; border-width: 1px 0 0 0; margin: 12px 0;" />
      <div class="hint">节点来源文件会显示在悬浮信息中，便于从图追踪到代码。</div>
    </aside>
    <main class="main">
      <div class="graph-card">
        <div id="graphContainer"></div>
      </div>
    </main>
  </div>

  <div id="tooltip" class="tooltip"></div>

  <div id="overlay" class="overlay">
    <div class="overlay-panel">
      <div class="overlay-head">
        <h2 id="overlayTitle" class="overlay-title"></h2>
        <button id="btnCloseOverlay" class="close-btn">关闭子图</button>
      </div>
      <div id="overlayGraph"></div>
    </div>
  </div>

  <script type="module">
    const BUNDLE = __BUNDLE_JSON__;
    const tooltipEl = document.getElementById("tooltip");
    const overlayEl = document.getElementById("overlay");
    const overlayTitleEl = document.getElementById("overlayTitle");
    const overlayGraphEl = document.getElementById("overlayGraph");
    const graphMetaEl = document.getElementById("graphMeta");
    const graphContainerEl = document.getElementById("graphContainer");
    const graphSelectEl = document.getElementById("graphSelect");
    const btnRootEl = document.getElementById("btnRoot");
    const btnCloseOverlayEl = document.getElementById("btnCloseOverlay");

    let renderCounter = 0;
    let mermaid = null;

    function escapeHtml(s) {{
      return String(s)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }}

    function buildTooltip(meta) {{
      const fields = Array.isArray(meta.state_fields) ? meta.state_fields.join(", ") : "";
      const lines = [
        `状态: ${{meta.title || meta.node_id}}`,
        meta.description ? `说明: ${{meta.description}}` : "",
        fields ? `关键字段: ${{fields}}` : "",
        meta.source_file ? `来源: ${{meta.source_file}}` : "",
        meta.subgraph_id ? `子图: ${{meta.subgraph_id}} (点击进入)` : "",
      ].filter(Boolean);
      return lines.join("\\n");
    }}

    function getNodeLabel(nodeEl) {{
      const textEl = nodeEl.querySelector(".nodeLabel, .label text, text");
      if (!textEl) return "";
      return textEl.textContent.trim();
    }}

    function setSideMeta(graph) {{
      graphMetaEl.textContent = [
        `图: ${{graph.title}}`,
        graph.description ? `说明: ${{graph.description}}` : "",
        `节点数: ${{Object.keys(graph.nodes || {{}}).length}}`,
      ].filter(Boolean).join("\\n");
    }}

    function withClickDirectives(graph) {{
      let mmd = graph.mermaid.trimEnd();
      const nodes = graph.nodes || {{}};
      const subgraphNodeIds = [];
      for (const [nodeId, meta] of Object.entries(nodes)) {{
        if (meta.subgraph_id && BUNDLE.graphs[meta.subgraph_id]) {{
          mmd += `\\nclick ${{nodeId}} call onGraphNodeClick(\\"${{graph.graph_id}}\\", \\"${{nodeId}}\\") \\"打开子图\\"`;
          subgraphNodeIds.push(nodeId);
        }}
      }}
      // 强制覆盖 mermaid 默认浅色节点风格，统一为深色底 + 浅亮边框。
      mmd += "\\nclassDef default fill:#141c2b,stroke:#8ddcff,stroke-width:1.2px,color:#e8edf5;";
      mmd += "\\nclassDef first fill:#141c2b,stroke:#8ddcff,stroke-width:1.2px,color:#e8edf5;";
      mmd += "\\nclassDef last fill:#141c2b,stroke:#8ddcff,stroke-width:1.2px,color:#e8edf5;";
      mmd += "\\nclassDef subgraphNode fill:#141c2b,stroke:#c6f0ff,stroke-width:2.6px,color:#e8edf5;";
      if (subgraphNodeIds.length > 0) {{
        mmd += `\\nclass ${{subgraphNodeIds.join(",")}} subgraphNode;`;
      }}
      return mmd;
    }}

    function bindNodeInteractions(containerEl, graph) {{
      const nodes = Array.from(containerEl.querySelectorAll("g.node, g[class*='node']"));
      for (const nodeEl of nodes) {{
        const label = getNodeLabel(nodeEl);
        if (!label) continue;
        const meta = graph.nodes?.[label];
        if (!meta) continue;

        if (meta.subgraph_id && BUNDLE.graphs[meta.subgraph_id]) {{
          nodeEl.classList.add("node-subgraph-hint");
          nodeEl.style.cursor = "pointer";
        }}

        nodeEl.addEventListener("mouseenter", () => {{
          tooltipEl.style.display = "block";
          tooltipEl.textContent = buildTooltip(meta);
        }});
        nodeEl.addEventListener("mousemove", (e) => {{
          tooltipEl.style.left = (e.clientX + 14) + "px";
          tooltipEl.style.top = (e.clientY + 14) + "px";
        }});
        nodeEl.addEventListener("mouseleave", () => {{
          tooltipEl.style.display = "none";
        }});
      }}
    }}

    async function renderGraph(targetEl, graph) {{
      const id = `g_${{graph.graph_id}}_${{renderCounter++}}`;
      const mmd = withClickDirectives(graph);
      const result = await mermaid.render(id, mmd);
      targetEl.innerHTML = result.svg;
      if (typeof result.bindFunctions === "function") {{
        result.bindFunctions(targetEl);
      }}
      bindNodeInteractions(targetEl, graph);
    }}

    window.onGraphNodeClick = function (graphId, nodeId) {{
      const graph = BUNDLE.graphs?.[graphId];
      const nodeMeta = graph?.nodes?.[nodeId];
      if (!nodeMeta) return;
      if (!nodeMeta.subgraph_id) return;
      const sub = BUNDLE.graphs?.[nodeMeta.subgraph_id];
      if (!sub) return;
      overlayTitleEl.textContent = `${{nodeMeta.title || nodeId}} / 子图`;
      renderGraph(overlayGraphEl, sub);
      overlayEl.classList.add("show");
    };

    function hideOverlay() {{
      overlayEl.classList.remove("show");
      overlayGraphEl.innerHTML = "";
    }}

    btnCloseOverlayEl.addEventListener("click", hideOverlay);
    overlayEl.addEventListener("click", (e) => {{
      if (e.target === overlayEl) hideOverlay();
    }});

    function loadGraphOptions() {{
      const ids = Object.keys(BUNDLE.graphs || {{}});
      for (const id of ids) {{
        const g = BUNDLE.graphs[id];
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = `${{g.title}} (${{id}})`;
        graphSelectEl.appendChild(opt);
      }}
      graphSelectEl.value = BUNDLE.root_graph_id || ids[0] || "";
    }}

    async function renderSelected() {{
      const graphId = graphSelectEl.value;
      const graph = BUNDLE.graphs?.[graphId];
      if (!graph) return;
      setSideMeta(graph);
      await renderGraph(graphContainerEl, graph);
    }}

    btnRootEl.addEventListener("click", async () => {{
      graphSelectEl.value = BUNDLE.root_graph_id;
      await renderSelected();
    }});
    graphSelectEl.addEventListener("change", renderSelected);

    async function loadMermaidModule() {{
      const candidates = [
        "./vendor/mermaid.esm.min.mjs",
        "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs",
      ];
      let lastError = null;
      for (const src of candidates) {{
        try {{
          const mod = await import(src);
          return mod.default || mod;
        }} catch (e) {{
          lastError = e;
        }}
      }}
      throw lastError || new Error("无法加载 mermaid 模块");
    }}

    async function boot() {{
      try {{
        mermaid = await loadMermaidModule();
        mermaid.initialize({{
          startOnLoad: false,
          securityLevel: "loose",
          theme: "dark",
          flowchart: {{ curve: "linear" }},
        }});
        loadGraphOptions();
        await renderSelected();
      }} catch (e) {{
        graphMetaEl.textContent = [
          "图渲染初始化失败。",
          "请优先使用本地 HTTP 服务打开，而不是直接 file:// 双击。",
          "建议命令：python -m http.server 8765 -d _GraphChat/docs/graphs",
          "然后访问：http://127.0.0.1:8765/graph_viewer.html",
          "",
          `错误: ${{String(e)}}`,
        ].join("\\n");
      }}
    }}

    boot();
  </script>
</body>
</html>
"""
    # 先还原模板中的双花括号，再注入 JSON，避免误伤 JSON 自身的大括号结构。
    html_template = html_template.replace("{{", "{").replace("}}", "}")
    html = html_template.replace("__BUNDLE_JSON__", bundle_json)
    html_path.write_text(html, encoding="utf-8")
    return html_path
