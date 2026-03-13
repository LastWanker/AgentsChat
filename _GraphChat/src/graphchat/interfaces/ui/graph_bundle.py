from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


NODE_DECL_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(")
EDGE_DECL_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*[-.=ox]+>\s*([A-Za-z_][A-Za-z0-9_]*)")


@dataclass
class GraphEntry:
    graph_id: str
    title: str
    description: str
    mermaid: str
    nodes: dict[str, dict[str, Any]]
    transitions: list[dict[str, Any]]


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


def _extract_mermaid_edges(mermaid_text: str) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for line in mermaid_text.splitlines():
        m = EDGE_DECL_RE.match(line.strip())
        if not m:
            continue
        out.add((m.group(1), m.group(2)))
    return out


def _graph_edges(compiled_graph) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in compiled_graph.get_graph().edges:
        source = str(getattr(item, "source", ""))
        target = str(getattr(item, "target", ""))
        if not source or not target:
            continue
        out.append(
            {
                "source": source,
                "target": target,
                "type": "conditional" if bool(getattr(item, "conditional", False)) else "edge",
                "note": "",
            }
        )
    return out


def build_graph_entry(
    graph_id: str,
    compiled_graph,
    graph_meta: dict | None = None,
) -> GraphEntry:
    mermaid = compiled_graph.get_graph().draw_mermaid()
    node_ids = _extract_node_ids(mermaid)
    mermaid_edges = _extract_mermaid_edges(mermaid)
    graph_meta = graph_meta or {}
    node_meta_map: dict[str, dict[str, Any]] = graph_meta.get("nodes", {})

    nodes: dict[str, dict[str, Any]] = {}
    for node_id in node_ids:
        base = {
            "node_id": node_id,
            "title": node_id,
            "description": "No metadata yet.",
            "source_file": "",
            "state_fields": [],
        }
        base.update(node_meta_map.get(node_id, {}))
        nodes[node_id] = base

    transitions = list(graph_meta.get("transitions", []))
    if not transitions:
        transitions = _graph_edges(compiled_graph)
    normalized_transitions: list[dict[str, Any]] = []
    for row in transitions:
        source = str(row.get("source", "")).strip()
        target = str(row.get("target", "")).strip()
        if not source or not target:
            continue
        edge_type = str(row.get("type", "edge")).strip().lower()
        normalized_transitions.append(
            {
                "source": source,
                "target": target,
                "type": edge_type or "edge",
                "note": str(row.get("note", "")).strip(),
                "rendered": (source, target) in mermaid_edges,
            }
        )

    return GraphEntry(
        graph_id=graph_id,
        title=graph_meta.get("title", graph_id),
        description=graph_meta.get("description", ""),
        mermaid=mermaid,
        nodes=nodes,
        transitions=normalized_transitions,
    )


def build_graph_bundle(graph_entries: list[GraphEntry], root_graph_id: str) -> dict[str, Any]:
    return {
        "version": "1.1.0",
        "root_graph_id": root_graph_id,
        "graphs": {
            entry.graph_id: {
                "graph_id": entry.graph_id,
                "title": entry.title,
                "description": entry.description,
                "mermaid": entry.mermaid,
                "nodes": entry.nodes,
                "transitions": entry.transitions,
            }
            for entry in graph_entries
        },
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
  <title>Graph 可视化</title>
  <style>
    :root {
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
      --badge-edge: #57d4a6;
      --badge-cond: #f6bf6f;
      --badge-send: #86b6ff;
      --badge-loop: #d58dff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Microsoft YaHei UI", "Noto Sans SC", sans-serif;
      background:
        radial-gradient(circle at 20% 15%, rgba(98,214,255,.18), transparent 38%),
        radial-gradient(circle at 80% 75%, rgba(74,255,166,.12), transparent 42%),
        linear-gradient(160deg, #0c0e14, #111726 70%);
      color: var(--text);
      min-height: 100vh;
    }
    .app {
      display: grid;
      grid-template-columns: 360px 1fr;
      min-height: 100vh;
      gap: 0;
    }
    .side {
      border-right: 1px solid var(--border);
      background: var(--panel);
      backdrop-filter: blur(8px);
      padding: 16px;
      overflow: auto;
    }
    .main {
      position: relative;
      padding: 16px;
    }
    h1 {
      font-size: 18px;
      margin: 0 0 12px 0;
      letter-spacing: .4px;
    }
    .hint {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
      margin-bottom: 12px;
    }
    select, button {
      width: 100%;
      border: 1px solid var(--border);
      background: var(--control-bg);
      color: var(--text);
      border-radius: 10px;
      padding: 8px 10px;
      margin-bottom: 10px;
    }
    select option {
      background: #0d1320;
      color: var(--text);
    }
    .meta {
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
      background: var(--card-bg);
      min-height: 88px;
      white-space: pre-wrap;
      font-size: 13px;
      line-height: 1.6;
      color: var(--muted);
      margin-bottom: 10px;
    }
    .flow {
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 8px;
      background: var(--card-bg);
      max-height: 46vh;
      overflow: auto;
      font-size: 12px;
    }
    .flow-item {
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 10px;
      padding: 8px;
      margin-bottom: 8px;
      background: rgba(8, 12, 20, 0.8);
      line-height: 1.5;
    }
    .badge {
      display: inline-block;
      border-radius: 999px;
      padding: 1px 8px;
      font-size: 11px;
      margin-right: 6px;
      color: #0c0f17;
      font-weight: 700;
    }
    .badge.edge { background: var(--badge-edge); }
    .badge.conditional { background: var(--badge-cond); }
    .badge.send { background: var(--badge-send); }
    .badge.loop { background: var(--badge-loop); }
    .missing {
      color: #ffb0a8;
      font-size: 11px;
    }
    .graph-card {
      border: 1px solid var(--border);
      border-radius: 16px;
      background: var(--card-bg);
      padding: 12px;
      overflow: auto;
      min-height: calc(100vh - 48px);
    }
    #graphContainer svg {
      max-width: 100%;
      height: auto;
    }
    .tooltip {
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
    }
    .overlay {
      position: fixed;
      inset: 0;
      display: none;
      z-index: 20;
      background: var(--glass);
      backdrop-filter: blur(9px);
      align-items: center;
      justify-content: center;
      padding: 28px;
    }
    .overlay.show { display: flex; }
    .overlay-panel {
      width: min(1100px, 96vw);
      max-height: 90vh;
      overflow: auto;
      border-radius: 16px;
      border: 1px solid var(--border);
      background: rgba(8, 12, 20, 0.94);
      padding: 14px 14px 8px 14px;
      box-shadow: 0 20px 40px rgba(0,0,0,.35);
    }
    .overlay-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;
    }
    .overlay-title {
      font-size: 16px;
      margin: 0;
    }
    .close-btn {
      width: auto;
      margin: 0;
      padding: 6px 10px;
      cursor: pointer;
    }
    .node-subgraph-hint {
      filter: drop-shadow(0 0 4px rgba(98,214,255,.45));
    }
    #graphContainer g.node-subgraph-hint rect,
    #graphContainer g.node-subgraph-hint polygon,
    #overlayGraph g.node-subgraph-hint rect,
    #overlayGraph g.node-subgraph-hint polygon {
      stroke: var(--accent-strong) !important;
      stroke-width: 1.6px !important;
    }
    #graphContainer g.node-subgraph-hint .label,
    #overlayGraph g.node-subgraph-hint .label {
      font-weight: 700;
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="side">
      <h1 id="sideTitle">Graph 可视化</h1>
      <div id="sideHint" class="hint">支持节点悬浮、子图点击、以及边类型说明（edge / conditional / send / loop）。</div>
      <div class="hint" style="margin-bottom:8px;">
        <label id="langLabel" for="langSelect">界面语言</label>
        <select id="langSelect" style="margin-top:6px;">
          <option value="zh">中文（默认）</option>
          <option value="en">English</option>
        </select>
      </div>
      <select id="graphSelect"></select>
      <button id="btnRoot">回到根图</button>
      <div id="graphMeta" class="meta">请选择图</div>
      <div id="flowMeta" class="flow"></div>
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
    const flowMetaEl = document.getElementById("flowMeta");
    const sideTitleEl = document.getElementById("sideTitle");
    const sideHintEl = document.getElementById("sideHint");
    const langLabelEl = document.getElementById("langLabel");
    const langSelectEl = document.getElementById("langSelect");

    let renderCounter = 0;
    let mermaid = null;
    let currentLang = "zh";

    const I18N = {
      zh: {
        docTitle: "Graph 可视化",
        sideTitle: "Graph 可视化",
        sideHint: "支持节点悬浮、子图点击、以及边类型说明（edge / conditional / send / loop）。",
        langLabel: "界面语言",
        btnRoot: "回到根图",
        graphMetaDefault: "请选择图",
        closeSubgraph: "关闭子图",
        nodeLabel: "节点",
        descLabel: "说明",
        fieldsLabel: "关键字段",
        sourceLabel: "来源",
        subgraphLabel: "子图",
        clickEnter: "点击进入",
        noTransitions: "无 transition 元数据",
        missingEdge: "Mermaid 未渲染该边（常见于 Send/动态路由）",
        graphLabel: "图",
        nodeCountLabel: "节点数",
        transitionsLabel: "Transitions",
        renderedLabel: "rendered",
        missingLabel: "missing",
        subgraphSuffix: "子图",
        clickOpenSubgraph: "打开子图",
        loadErrorTitle: "图渲染初始化失败。",
        loadErrorTip1: "请优先使用本地 HTTP 服务打开，而不是直接 file:// 双击。",
        loadErrorTip2: "建议命令: python -m http.server 8765 -d _GraphChat/docs/graphs",
        loadErrorTip3: "然后访问: http://127.0.0.1:8765/graph_viewer.html",
        errorLabel: "错误",
      },
      en: {
        docTitle: "Graph Viewer",
        sideTitle: "Graph Viewer",
        sideHint: "Hover nodes, click subgraph nodes, and inspect transition types (edge / conditional / send / loop).",
        langLabel: "Language",
        btnRoot: "Back To Root",
        graphMetaDefault: "Please select a graph",
        closeSubgraph: "Close Subgraph",
        nodeLabel: "Node",
        descLabel: "Description",
        fieldsLabel: "Fields",
        sourceLabel: "Source",
        subgraphLabel: "Subgraph",
        clickEnter: "click to open",
        noTransitions: "No transition metadata",
        missingEdge: "This edge is not rendered by Mermaid (common for Send/dynamic routing)",
        graphLabel: "Graph",
        nodeCountLabel: "Node count",
        transitionsLabel: "Transitions",
        renderedLabel: "rendered",
        missingLabel: "missing",
        subgraphSuffix: "Subgraph",
        clickOpenSubgraph: "Open Subgraph",
        loadErrorTitle: "Failed to initialize graph rendering.",
        loadErrorTip1: "Use a local HTTP server instead of opening with file:// directly.",
        loadErrorTip2: "Suggested command: python -m http.server 8765 -d _GraphChat/docs/graphs",
        loadErrorTip3: "Then visit: http://127.0.0.1:8765/graph_viewer.html",
        errorLabel: "Error",
      },
    };

    function t(key) {
      const pack = I18N[currentLang] || I18N.zh;
      return pack[key] || I18N.zh[key] || key;
    }

    function applyLanguage(lang) {
      currentLang = lang === "en" ? "en" : "zh";
      document.documentElement.lang = currentLang === "zh" ? "zh-CN" : "en";
      document.title = t("docTitle");
      sideTitleEl.textContent = t("sideTitle");
      sideHintEl.textContent = t("sideHint");
      langLabelEl.textContent = t("langLabel");
      btnRootEl.textContent = t("btnRoot");
      btnCloseOverlayEl.textContent = t("closeSubgraph");
      if (!(graphMetaEl.dataset && graphMetaEl.dataset.populated === "1")) {
        graphMetaEl.textContent = t("graphMetaDefault");
      }
      localStorage.setItem("graph_viewer_lang", currentLang);
    }

    function buildTooltip(meta) {
      const fields = Array.isArray(meta.state_fields) ? meta.state_fields.join(", ") : "";
      const lines = [
        `${t("nodeLabel")}: ${meta.title || meta.node_id}`,
        meta.description ? `${t("descLabel")}: ${meta.description}` : "",
        fields ? `${t("fieldsLabel")}: ${fields}` : "",
        meta.source_file ? `${t("sourceLabel")}: ${meta.source_file}` : "",
        meta.subgraph_id ? `${t("subgraphLabel")}: ${meta.subgraph_id} (${t("clickEnter")})` : "",
      ].filter(Boolean);
      return lines.join("\\n");
    }

    function getNodeLabel(nodeEl) {
      const textEl = nodeEl.querySelector(".nodeLabel, .label text, text");
      if (!textEl) return "";
      return textEl.textContent.trim();
    }

    function badgeClass(edgeType) {
      if (edgeType === "conditional") return "conditional";
      if (edgeType === "send") return "send";
      if (edgeType === "loop") return "loop";
      return "edge";
    }

    function renderTransitions(graph) {
      const transitions = Array.isArray(graph.transitions) ? graph.transitions : [];
      if (!transitions.length) {
        flowMetaEl.innerHTML = `<div class='hint'>${t("noTransitions")}</div>`;
        return;
      }
      const items = transitions.map((row) => {
        const type = String(row.type || "edge");
        const note = String(row.note || "");
        const missing = row.rendered === false ? `<div class='missing'>${t("missingEdge")}</div>` : "";
        return [
          "<div class='flow-item'>",
          `<span class='badge ${badgeClass(type)}'>${type}</span>`,
          `<code>${row.source}</code> → <code>${row.target}</code>`,
          note ? `<div>${note}</div>` : "",
          missing,
          "</div>",
        ].join("");
      });
      flowMetaEl.innerHTML = items.join("");
    }

    function setSideMeta(graph) {
      const transitions = Array.isArray(graph.transitions) ? graph.transitions : [];
      const rendered = transitions.filter((t) => t.rendered !== false).length;
      const missing = transitions.length - rendered;
      graphMetaEl.textContent = [
        `${t("graphLabel")}: ${graph.title}`,
        graph.description ? `${t("descLabel")}: ${graph.description}` : "",
        `${t("nodeCountLabel")}: ${Object.keys(graph.nodes || {}).length}`,
        `${t("transitionsLabel")}: ${transitions.length} (${t("renderedLabel")}=${rendered}, ${t("missingLabel")}=${missing})`,
      ].filter(Boolean).join("\\n");
      graphMetaEl.dataset.populated = "1";
      renderTransitions(graph);
    }

    function withClickDirectives(graph) {
      let mmd = graph.mermaid.trimEnd();
      const nodes = graph.nodes || {};
      const subgraphNodeIds = [];
      for (const [nodeId, meta] of Object.entries(nodes)) {
        if (meta.subgraph_id && BUNDLE.graphs[meta.subgraph_id]) {
          mmd += `\\nclick ${nodeId} call onGraphNodeClick(\\"${graph.graph_id}\\", \\"${nodeId}\\") \\"${t("clickOpenSubgraph")}\\"`;
          subgraphNodeIds.push(nodeId);
        }
      }
      mmd += "\\nclassDef default fill:#141c2b,stroke:#8ddcff,stroke-width:1.2px,color:#e8edf5;";
      mmd += "\\nclassDef first fill-opacity:0";
      mmd += "\\nclassDef last fill:#141c2b,stroke:#8ddcff,stroke-width:1.2px,color:#e8edf5;";
      mmd += "\\nclassDef subgraphNode fill:#141c2b,stroke:#c6f0ff,stroke-width:2.6px,color:#e8edf5;";
      if (subgraphNodeIds.length > 0) {
        mmd += `\\nclass ${subgraphNodeIds.join(",")} subgraphNode;`;
      }
      return mmd;
    }

    function bindNodeInteractions(containerEl, graph) {
      const nodes = Array.from(containerEl.querySelectorAll("g.node, g[class*='node']"));
      for (const nodeEl of nodes) {
        const label = getNodeLabel(nodeEl);
        if (!label) continue;
        const meta = graph.nodes?.[label];
        if (!meta) continue;
        if (meta.subgraph_id && BUNDLE.graphs[meta.subgraph_id]) {
          nodeEl.classList.add("node-subgraph-hint");
          nodeEl.style.cursor = "pointer";
        }
        nodeEl.addEventListener("mouseenter", () => {
          tooltipEl.style.display = "block";
          tooltipEl.textContent = buildTooltip(meta);
        });
        nodeEl.addEventListener("mousemove", (e) => {
          tooltipEl.style.left = (e.clientX + 14) + "px";
          tooltipEl.style.top = (e.clientY + 14) + "px";
        });
        nodeEl.addEventListener("mouseleave", () => {
          tooltipEl.style.display = "none";
        });
      }
    }

    async function renderGraph(targetEl, graph) {
      const id = `g_${graph.graph_id}_${renderCounter++}`;
      const mmd = withClickDirectives(graph);
      const result = await mermaid.render(id, mmd);
      targetEl.innerHTML = result.svg;
      if (typeof result.bindFunctions === "function") {
        result.bindFunctions(targetEl);
      }
      bindNodeInteractions(targetEl, graph);
    }

    window.onGraphNodeClick = function (graphId, nodeId) {
      const graph = BUNDLE.graphs?.[graphId];
      const nodeMeta = graph?.nodes?.[nodeId];
      if (!nodeMeta?.subgraph_id) return;
      const sub = BUNDLE.graphs?.[nodeMeta.subgraph_id];
      if (!sub) return;
      overlayTitleEl.textContent = `${nodeMeta.title || nodeId} / ${t("subgraphSuffix")}`;
      renderGraph(overlayGraphEl, sub);
      overlayEl.classList.add("show");
    };

    function hideOverlay() {
      overlayEl.classList.remove("show");
      overlayGraphEl.innerHTML = "";
    }

    btnCloseOverlayEl.addEventListener("click", hideOverlay);
    overlayEl.addEventListener("click", (e) => {
      if (e.target === overlayEl) hideOverlay();
    });

    function loadGraphOptions() {
      const ids = Object.keys(BUNDLE.graphs || {});
      for (const id of ids) {
        const g = BUNDLE.graphs[id];
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = `${g.title} (${id})`;
        graphSelectEl.appendChild(opt);
      }
      graphSelectEl.value = BUNDLE.root_graph_id || ids[0] || "";
    }

    async function renderSelected() {
      const graphId = graphSelectEl.value;
      const graph = BUNDLE.graphs?.[graphId];
      if (!graph) return;
      setSideMeta(graph);
      await renderGraph(graphContainerEl, graph);
    }

    btnRootEl.addEventListener("click", async () => {
      graphSelectEl.value = BUNDLE.root_graph_id;
      await renderSelected();
    });
    graphSelectEl.addEventListener("change", renderSelected);
    langSelectEl.addEventListener("change", async () => {
      applyLanguage(langSelectEl.value);
      await renderSelected();
    });

    async function loadMermaidModule() {
      const candidates = [
        "./vendor/mermaid.esm.min.mjs",
        "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs",
      ];
      let lastError = null;
      for (const src of candidates) {
        try {
          const mod = await import(src);
          return mod.default || mod;
        } catch (e) {
          lastError = e;
        }
      }
      throw lastError || new Error("无法加载 mermaid 模块");
    }

    async function boot() {
      try {
        mermaid = await loadMermaidModule();
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "loose",
          theme: "dark",
          flowchart: { curve: "linear" },
        });
        loadGraphOptions();
        await renderSelected();
      } catch (e) {
        graphMetaEl.textContent = [
          t("loadErrorTitle"),
          t("loadErrorTip1"),
          t("loadErrorTip2"),
          t("loadErrorTip3"),
          "",
          `${t("errorLabel")}: ${String(e)}`,
        ].join("\\n");
      }
    }

    const savedLang = localStorage.getItem("graph_viewer_lang");
    langSelectEl.value = savedLang === "en" ? "en" : "zh";
    applyLanguage(langSelectEl.value);
    boot();
  </script>
</body>
</html>
"""
    html = html_template.replace("__BUNDLE_JSON__", bundle_json)
    html_path.write_text(html, encoding="utf-8")
    return html_path
