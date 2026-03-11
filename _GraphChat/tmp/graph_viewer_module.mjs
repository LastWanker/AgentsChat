
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";

    const BUNDLE = {"version": "1.0.0", "root_graph_id": "agent", "graphs": {"world": {"graph_id": "world", "title": "WorldGraph", "description": "世界图：事件摄入、路由、并发分发、提交与发布。", "mermaid": "---\nconfig:\n  flowchart:\n    curve: linear\n---\ngraph TD;\n\t__start__(<p>__start__</p>)\n\tingest_events(ingest_events)\n\troute_scope(route_scope)\n\tselect_runnable_agents(select_runnable_agents)\n\trun_agent(run_agent)\n\tcollect_agent_outputs(collect_agent_outputs)\n\tcommit_events(commit_events)\n\tpublish_updates(publish_updates)\n\tidle_check(idle_check)\n\t__end__(<p>__end__</p>)\n\t__start__ --> ingest_events;\n\tingest_events --> route_scope;\n\troute_scope --> select_runnable_agents;\n\tselect_runnable_agents --> __end__;\n\tclassDef default fill:#f2f0ff,line-height:1.2\n\tclassDef first fill-opacity:0\n\tclassDef last fill:#bfb6fc\n", "nodes": {"__start__": {"node_id": "__start__", "title": "__start__", "description": "待补充节点说明", "source_file": "", "state_fields": []}, "ingest_events": {"node_id": "ingest_events", "title": "摄入事件", "description": "接收用户/Boss/系统输入，合并到待处理队列。", "source_file": "src/graphchat/application/nodes/world_nodes.py", "state_fields": ["incoming_events", "pending_events"]}, "route_scope": {"node_id": "route_scope", "title": "Scope 路由", "description": "按主群/小群/私聊规则决定可见性。", "source_file": "src/graphchat/application/nodes/world_nodes.py", "state_fields": ["pending_events", "routed_events"]}, "select_runnable_agents": {"node_id": "select_runnable_agents", "title": "选择可运行 Agent", "description": "根据路由结果形成本轮 agent 任务。", "source_file": "src/graphchat/application/nodes/world_nodes.py", "state_fields": ["agents", "agent_tasks", "runnable_agents"]}, "run_agent": {"node_id": "run_agent", "title": "并发运行 Agent", "description": "通过 Send 并发进入 AgentGraph。", "source_file": "src/graphchat/application/nodes/world_nodes.py", "state_fields": ["agent_task", "agent_outputs"]}, "collect_agent_outputs": {"node_id": "collect_agent_outputs", "title": "汇总输出", "description": "聚合各 Agent 产出事件。", "source_file": "src/graphchat/application/nodes/world_nodes.py", "state_fields": ["agent_outputs"]}, "commit_events": {"node_id": "commit_events", "title": "提交事件", "description": "持久化事件到事实层存储。", "source_file": "src/graphchat/application/nodes/world_nodes.py", "state_fields": ["agent_outputs", "committed_event_ids"]}, "publish_updates": {"node_id": "publish_updates", "title": "发布更新", "description": "对外发布本轮事件更新。", "source_file": "src/graphchat/application/nodes/world_nodes.py", "state_fields": ["published_events"]}, "idle_check": {"node_id": "idle_check", "title": "空闲检查", "description": "本轮收尾并推进世界时钟。", "source_file": "src/graphchat/application/nodes/world_nodes.py", "state_fields": ["tick"]}, "__end__": {"node_id": "__end__", "title": "__end__", "description": "待补充节点说明", "source_file": "", "state_fields": []}}}, "agent": {"graph_id": "agent", "title": "AgentGraph", "description": "Agent 行为图：倾听、决策、检索、治理、守卫、输出。", "mermaid": "---\nconfig:\n  flowchart:\n    curve: linear\n---\ngraph TD;\n\t__start__([<p>__start__</p>]):::first\n\tlistening(listening)\n\tsilent_loop_subgraph(silent_loop_subgraph)\n\tdecide_wake(decide_wake)\n\tplan_action(plan_action)\n\tretrieval_subgraph(retrieval_subgraph)\n\tcitation_guard(citation_guard)\n\tboard_subgraph(board_subgraph)\n\tgovernance_subgraph(governance_subgraph)\n\tpolicy_gate(policy_gate)\n\tschema_guard(schema_guard)\n\taction_registry_guard(action_registry_guard)\n\tidempotency_guard(idempotency_guard)\n\temit_event(emit_event)\n\t__end__([<p>__end__</p>]):::last\n\t__start__ --> listening;\n\taction_registry_guard --> idempotency_guard;\n\tboard_subgraph --> governance_subgraph;\n\tcitation_guard --> board_subgraph;\n\tdecide_wake -.-> __end__;\n\tdecide_wake -.-> plan_action;\n\tgovernance_subgraph --> policy_gate;\n\tidempotency_guard --> emit_event;\n\tlistening --> silent_loop_subgraph;\n\tplan_action -.-> citation_guard;\n\tplan_action -.-> retrieval_subgraph;\n\tpolicy_gate --> schema_guard;\n\tretrieval_subgraph --> citation_guard;\n\tschema_guard --> action_registry_guard;\n\tsilent_loop_subgraph --> decide_wake;\n\temit_event --> __end__;\n\tclassDef default fill:#f2f0ff,line-height:1.2\n\tclassDef first fill-opacity:0\n\tclassDef last fill:#bfb6fc\n", "nodes": {"__start__": {"node_id": "__start__", "title": "__start__", "description": "待补充节点说明", "source_file": "", "state_fields": []}, "listening": {"node_id": "listening", "title": "倾听", "description": "读取当前可见窗口，更新 last_event。", "source_file": "src/graphchat/application/nodes/agent_nodes.py", "state_fields": ["visible_events", "last_event"]}, "silent_loop_subgraph": {"node_id": "silent_loop_subgraph", "title": "静默循环子图", "description": "低频轮询 + 唤醒判定。", "source_file": "src/graphchat/application/graphs/subgraphs/silent_loop_subgraph.py", "state_fields": ["silent_rounds", "max_silent_rounds", "should_wake"], "subgraph_id": "silent_loop_subgraph"}, "decide_wake": {"node_id": "decide_wake", "title": "唤醒决策", "description": "判断是否进入本轮行动。", "source_file": "src/graphchat/application/nodes/agent_nodes.py", "state_fields": ["should_wake"]}, "plan_action": {"node_id": "plan_action", "title": "行动规划", "description": "根据上下文输出结构化动作与策略。", "source_file": "src/graphchat/application/nodes/agent_nodes.py", "state_fields": ["planned_action", "citation_policy", "needs_retrieval"]}, "retrieval_subgraph": {"node_id": "retrieval_subgraph", "title": "检索子图", "description": "多通道召回并形成候选证据。", "source_file": "src/graphchat/application/graphs/subgraphs/retrieval_subgraph.py", "state_fields": ["retrieval_channel", "candidates", "focus_reference"], "subgraph_id": "retrieval_subgraph"}, "citation_guard": {"node_id": "citation_guard", "title": "引用守卫", "description": "按 citation_policy 校验引用完整性。", "source_file": "src/graphchat/application/guards/citation_guard.py", "state_fields": ["citation_policy", "focus_reference", "candidates"]}, "board_subgraph": {"node_id": "board_subgraph", "title": "任务板子图", "description": "读取/维护任务板与记录板。", "source_file": "src/graphchat/application/graphs/subgraphs/board_subgraph.py", "state_fields": ["board_snapshot", "board_operation"], "subgraph_id": "board_subgraph"}, "governance_subgraph": {"node_id": "governance_subgraph", "title": "治理子图", "description": "投票、解散群等治理动作处理。", "source_file": "src/graphchat/application/graphs/subgraphs/governance_subgraph.py", "state_fields": ["action_payload", "approval_required"], "subgraph_id": "governance_subgraph"}, "policy_gate": {"node_id": "policy_gate", "title": "策略闸门", "description": "命中高风险动作时触发 interrupt。", "source_file": "src/graphchat/application/nodes/agent_nodes.py", "state_fields": ["approval_required", "approval_decision"]}, "schema_guard": {"node_id": "schema_guard", "title": "结构守卫", "description": "校验输出字段合法性。", "source_file": "src/graphchat/application/guards/schema_guard.py", "state_fields": ["planned_action", "action_payload"]}, "action_registry_guard": {"node_id": "action_registry_guard", "title": "动作守卫", "description": "动作是否在注册表内且启用。", "source_file": "src/graphchat/application/guards/action_registry_guard.py", "state_fields": ["planned_action"]}, "idempotency_guard": {"node_id": "idempotency_guard", "title": "幂等守卫", "description": "避免重复副作用触发。", "source_file": "src/graphchat/application/guards/idempotency_guard.py", "state_fields": ["idempotency_key"]}, "emit_event": {"node_id": "emit_event", "title": "事件落地", "description": "输出标准事件并写入 trace。", "source_file": "src/graphchat/application/nodes/agent_nodes.py", "state_fields": ["emitted_events", "trace"]}, "__end__": {"node_id": "__end__", "title": "__end__", "description": "待补充节点说明", "source_file": "", "state_fields": []}}}, "silent_loop_subgraph": {"graph_id": "silent_loop_subgraph", "title": "SilentLoopSubgraph", "description": "静默循环子图。", "mermaid": "---\nconfig:\n  flowchart:\n    curve: linear\n---\ngraph TD;\n\t__start__([<p>__start__</p>]):::first\n\tpoll_new_events(poll_new_events)\n\tbackoff_control(backoff_control)\n\twake_signal_filter(wake_signal_filter)\n\t__end__([<p>__end__</p>]):::last\n\t__start__ --> poll_new_events;\n\tbackoff_control --> wake_signal_filter;\n\tpoll_new_events --> backoff_control;\n\twake_signal_filter --> __end__;\n\tclassDef default fill:#f2f0ff,line-height:1.2\n\tclassDef first fill-opacity:0\n\tclassDef last fill:#bfb6fc\n", "nodes": {"__start__": {"node_id": "__start__", "title": "__start__", "description": "待补充节点说明", "source_file": "", "state_fields": []}, "poll_new_events": {"node_id": "poll_new_events", "title": "轮询新事件", "description": "检测 mention 与外部信号。", "source_file": "src/graphchat/application/graphs/subgraphs/silent_loop_subgraph.py", "state_fields": ["last_event", "wake_mention"]}, "backoff_control": {"node_id": "backoff_control", "title": "退避控制", "description": "静默轮数累积与节奏控制。", "source_file": "src/graphchat/application/graphs/subgraphs/silent_loop_subgraph.py", "state_fields": ["silent_rounds"]}, "wake_signal_filter": {"node_id": "wake_signal_filter", "title": "唤醒过滤", "description": "根据规则决定是否唤醒。", "source_file": "src/graphchat/application/graphs/subgraphs/silent_loop_subgraph.py", "state_fields": ["should_wake", "max_silent_rounds"]}, "__end__": {"node_id": "__end__", "title": "__end__", "description": "待补充节点说明", "source_file": "", "state_fields": []}}}, "retrieval_subgraph": {"graph_id": "retrieval_subgraph", "title": "RetrievalSubgraph", "description": "检索通道子图。", "mermaid": "---\nconfig:\n  flowchart:\n    curve: linear\n---\ngraph TD;\n\t__start__([<p>__start__</p>]):::first\n\tchoose_channel(choose_channel)\n\tretrieve_candidates(retrieve_candidates)\n\trank_candidates(rank_candidates)\n\t__end__([<p>__end__</p>]):::last\n\t__start__ --> choose_channel;\n\tchoose_channel --> retrieve_candidates;\n\tretrieve_candidates --> rank_candidates;\n\trank_candidates --> __end__;\n\tclassDef default fill:#f2f0ff,line-height:1.2\n\tclassDef first fill-opacity:0\n\tclassDef last fill:#bfb6fc\n", "nodes": {"__start__": {"node_id": "__start__", "title": "__start__", "description": "待补充节点说明", "source_file": "", "state_fields": []}, "choose_channel": {"node_id": "choose_channel", "title": "选择通道", "description": "根据动作类型选择检索通道。", "source_file": "src/graphchat/application/graphs/subgraphs/retrieval_subgraph.py", "state_fields": ["planned_action", "retrieval_channel"]}, "retrieve_candidates": {"node_id": "retrieve_candidates", "title": "召回候选", "description": "从历史/索引等来源召回候选事件。", "source_file": "src/graphchat/application/graphs/subgraphs/retrieval_subgraph.py", "state_fields": ["visible_events", "candidates"]}, "rank_candidates": {"node_id": "rank_candidates", "title": "候选排序", "description": "确定 focus 与 support 引用。", "source_file": "src/graphchat/application/graphs/subgraphs/retrieval_subgraph.py", "state_fields": ["focus_reference", "support_references"]}, "__end__": {"node_id": "__end__", "title": "__end__", "description": "待补充节点说明", "source_file": "", "state_fields": []}}}, "board_subgraph": {"graph_id": "board_subgraph", "title": "BoardSubgraph", "description": "任务板维护子图。", "mermaid": "---\nconfig:\n  flowchart:\n    curve: linear\n---\ngraph TD;\n\t__start__([<p>__start__</p>]):::first\n\tboard_read(board_read)\n\tboard_update(board_update)\n\t__end__([<p>__end__</p>]):::last\n\t__start__ --> board_read;\n\tboard_read --> board_update;\n\tboard_update --> __end__;\n\tclassDef default fill:#f2f0ff,line-height:1.2\n\tclassDef first fill-opacity:0\n\tclassDef last fill:#bfb6fc\n", "nodes": {"__start__": {"node_id": "__start__", "title": "__start__", "description": "待补充节点说明", "source_file": "", "state_fields": []}, "board_read": {"node_id": "board_read", "title": "读取任务板", "description": "加载当前任务板快照。", "source_file": "src/graphchat/application/graphs/subgraphs/board_subgraph.py", "state_fields": ["board_snapshot"]}, "board_update": {"node_id": "board_update", "title": "更新任务板", "description": "新增/更新板项（当前最小实现）。", "source_file": "src/graphchat/application/graphs/subgraphs/board_subgraph.py", "state_fields": ["board_operation", "action_payload"]}, "__end__": {"node_id": "__end__", "title": "__end__", "description": "待补充节点说明", "source_file": "", "state_fields": []}}}, "governance_subgraph": {"graph_id": "governance_subgraph", "title": "GovernanceSubgraph", "description": "治理动作子图。", "mermaid": "---\nconfig:\n  flowchart:\n    curve: linear\n---\ngraph TD;\n\t__start__([<p>__start__</p>]):::first\n\tgovernance_prepare(governance_prepare)\n\t__end__([<p>__end__</p>]):::last\n\t__start__ --> governance_prepare;\n\tgovernance_prepare --> __end__;\n\tclassDef default fill:#f2f0ff,line-height:1.2\n\tclassDef first fill-opacity:0\n\tclassDef last fill:#bfb6fc\n", "nodes": {"__start__": {"node_id": "__start__", "title": "__start__", "description": "待补充节点说明", "source_file": "", "state_fields": []}, "governance_prepare": {"node_id": "governance_prepare", "title": "治理准备", "description": "投票/解散群动作载荷标准化。", "source_file": "src/graphchat/application/graphs/subgraphs/governance_subgraph.py", "state_fields": ["planned_action", "action_payload"]}, "__end__": {"node_id": "__end__", "title": "__end__", "description": "待补充节点说明", "source_file": "", "state_fields": []}}}}};
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

    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "loose",
      theme: "dark",
      flowchart: { curve: "linear" },
    });

    function escapeHtml(s) {
      return String(s)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }

    function buildTooltip(meta) {
      const fields = Array.isArray(meta.state_fields) ? meta.state_fields.join(", ") : "";
      const lines = [
        `状态: ${meta.title || meta.node_id}`,
        meta.description ? `说明: ${meta.description}` : "",
        fields ? `关键字段: ${fields}` : "",
        meta.source_file ? `来源: ${meta.source_file}` : "",
        meta.subgraph_id ? `子图: ${meta.subgraph_id} (点击进入)` : "",
      ].filter(Boolean);
      return lines.join("\n");
    }

    function getNodeLabel(nodeEl) {
      const textEl = nodeEl.querySelector(".nodeLabel, .label text, text");
      if (!textEl) return "";
      return textEl.textContent.trim();
    }

    function setSideMeta(graph) {
      graphMetaEl.textContent = [
        `图: ${graph.title}`,
        graph.description ? `说明: ${graph.description}` : "",
        `节点数: ${Object.keys(graph.nodes || {}).length}`,
      ].filter(Boolean).join("\n");
    }

    function withClickDirectives(graph) {
      let mmd = graph.mermaid.trimEnd();
      const nodes = graph.nodes || {};
      for (const [nodeId, meta] of Object.entries(nodes)) {
        if (meta.subgraph_id && BUNDLE.graphs[meta.subgraph_id]) {
          mmd += `\nclick ${nodeId} call onGraphNodeClick(\"${graph.graph_id}\", \"${nodeId}\") \"打开子图\"`;
        }
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
      if (!nodeMeta) return;
      if (!nodeMeta.subgraph_id) return;
      const sub = BUNDLE.graphs?.[nodeMeta.subgraph_id];
      if (!sub) return;
      overlayTitleEl.textContent = `${nodeMeta.title || nodeId} / 子图`;
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

    loadGraphOptions();
    renderSelected();
  