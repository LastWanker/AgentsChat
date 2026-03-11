from __future__ import annotations

# 图节点元数据：用于可视化层展示，不参与运行逻辑。
# 待拓展：可迁移到 YAML/JSON 配置，使其他项目无需改代码即可复用查看器。
GRAPH_METADATA: dict[str, dict] = {
    "world": {
        "title": "WorldGraph",
        "description": "世界图：事件摄入、路由、并发分发、提交与发布。",
        "nodes": {
            "ingest_events": {
                "title": "摄入事件",
                "description": "接收用户/Boss/系统输入，合并到待处理队列。",
                "source_file": "src/graphchat/application/nodes/world_nodes.py",
                "state_fields": ["incoming_events", "pending_events"],
            },
            "route_scope": {
                "title": "Scope 路由",
                "description": "按主群/小群/私聊规则决定可见性。",
                "source_file": "src/graphchat/application/nodes/world_nodes.py",
                "state_fields": ["pending_events", "routed_events"],
            },
            "select_runnable_agents": {
                "title": "选择可运行 Agent",
                "description": "根据路由结果形成本轮 agent 任务。",
                "source_file": "src/graphchat/application/nodes/world_nodes.py",
                "state_fields": ["agents", "agent_tasks", "runnable_agents"],
            },
            "run_agent": {
                "title": "并发运行 Agent",
                "description": "通过 Send 并发进入 AgentGraph。",
                "source_file": "src/graphchat/application/nodes/world_nodes.py",
                "state_fields": ["agent_task", "agent_outputs"],
            },
            "collect_agent_outputs": {
                "title": "汇总输出",
                "description": "聚合各 Agent 产出事件。",
                "source_file": "src/graphchat/application/nodes/world_nodes.py",
                "state_fields": ["agent_outputs"],
            },
            "commit_events": {
                "title": "提交事件",
                "description": "持久化事件到事实层存储。",
                "source_file": "src/graphchat/application/nodes/world_nodes.py",
                "state_fields": ["agent_outputs", "committed_event_ids"],
            },
            "publish_updates": {
                "title": "发布更新",
                "description": "对外发布本轮事件更新。",
                "source_file": "src/graphchat/application/nodes/world_nodes.py",
                "state_fields": ["published_events"],
            },
            "idle_check": {
                "title": "空闲检查",
                "description": "本轮收尾并推进世界时钟。",
                "source_file": "src/graphchat/application/nodes/world_nodes.py",
                "state_fields": ["tick"],
            },
        },
    },
    "agent": {
        "title": "AgentGraph",
        "description": "Agent 行为图：倾听、决策、检索、治理、守卫、输出。",
        "nodes": {
            "listening": {
                "title": "倾听",
                "description": "读取当前可见窗口，更新 last_event。",
                "source_file": "src/graphchat/application/nodes/agent_nodes.py",
                "state_fields": ["visible_events", "last_event"],
            },
            "silent_loop_subgraph": {
                "title": "静默循环子图",
                "description": "低频轮询 + 唤醒判定。",
                "source_file": "src/graphchat/application/graphs/subgraphs/silent_loop_subgraph.py",
                "state_fields": ["silent_rounds", "max_silent_rounds", "should_wake"],
                "subgraph_id": "silent_loop_subgraph",
            },
            "decide_wake": {
                "title": "唤醒决策",
                "description": "判断是否进入本轮行动。",
                "source_file": "src/graphchat/application/nodes/agent_nodes.py",
                "state_fields": ["should_wake"],
            },
            "plan_action": {
                "title": "行动规划",
                "description": "根据上下文输出结构化动作与策略。",
                "source_file": "src/graphchat/application/nodes/agent_nodes.py",
                "state_fields": ["planned_action", "citation_policy", "needs_retrieval"],
            },
            "retrieval_subgraph": {
                "title": "检索子图",
                "description": "多通道可开关召回 + 规则融合评分。",
                "source_file": "src/graphchat/application/graphs/subgraphs/retrieval_subgraph.py",
                "state_fields": [
                    "retrieval_channel",
                    "retrieval_channels",
                    "candidates",
                    "focus_reference",
                    "retrieval_trace",
                ],
                "subgraph_id": "retrieval_subgraph",
            },
            "citation_guard": {
                "title": "引用守卫",
                "description": "按 citation_policy 校验引用完整性。",
                "source_file": "src/graphchat/application/guards/citation_guard.py",
                "state_fields": ["citation_policy", "focus_reference", "candidates"],
            },
            "board_subgraph": {
                "title": "任务板子图",
                "description": "读取/维护任务板与记录板（含归档/删除/优先级/截止时间）。",
                "source_file": "src/graphchat/application/graphs/subgraphs/board_subgraph.py",
                "state_fields": ["board_snapshot", "board_operation"],
                "subgraph_id": "board_subgraph",
            },
            "governance_subgraph": {
                "title": "治理子图",
                "description": "投票、解散群等治理动作处理。",
                "source_file": "src/graphchat/application/graphs/subgraphs/governance_subgraph.py",
                "state_fields": ["action_payload", "approval_required"],
                "subgraph_id": "governance_subgraph",
            },
            "policy_gate": {
                "title": "策略闸门",
                "description": "命中高风险动作时触发 interrupt。",
                "source_file": "src/graphchat/application/nodes/agent_nodes.py",
                "state_fields": ["approval_required", "approval_decision"],
            },
            "schema_guard": {
                "title": "结构守卫",
                "description": "校验输出字段合法性。",
                "source_file": "src/graphchat/application/guards/schema_guard.py",
                "state_fields": ["planned_action", "action_payload"],
            },
            "action_registry_guard": {
                "title": "动作守卫",
                "description": "动作是否在注册表内且启用。",
                "source_file": "src/graphchat/application/guards/action_registry_guard.py",
                "state_fields": ["planned_action"],
            },
            "idempotency_guard": {
                "title": "幂等守卫",
                "description": "避免重复副作用触发。",
                "source_file": "src/graphchat/application/guards/idempotency_guard.py",
                "state_fields": ["idempotency_key"],
            },
            "emit_event": {
                "title": "事件落地",
                "description": "输出标准事件并写入 trace。",
                "source_file": "src/graphchat/application/nodes/agent_nodes.py",
                "state_fields": ["emitted_events", "trace"],
            },
        },
    },
    "silent_loop_subgraph": {
        "title": "SilentLoopSubgraph",
        "description": "静默循环子图。",
        "nodes": {
            "poll_new_events": {
                "title": "轮询新事件",
                "description": "检测 mention 与外部信号。",
                "source_file": "src/graphchat/application/graphs/subgraphs/silent_loop_subgraph.py",
                "state_fields": ["last_event", "wake_mention"],
            },
            "backoff_control": {
                "title": "退避控制",
                "description": "静默轮数累积与节奏控制。",
                "source_file": "src/graphchat/application/graphs/subgraphs/silent_loop_subgraph.py",
                "state_fields": ["silent_rounds"],
            },
            "wake_signal_filter": {
                "title": "唤醒过滤",
                "description": "根据规则决定是否唤醒。",
                "source_file": "src/graphchat/application/graphs/subgraphs/silent_loop_subgraph.py",
                "state_fields": ["should_wake", "max_silent_rounds"],
            },
        },
    },
    "retrieval_subgraph": {
        "title": "RetrievalSubgraph",
        "description": "检索通道子图。",
        "nodes": {
            "choose_channel": {
                "title": "选择通道",
                "description": "根据动作类型与通道开关选择召回通道。",
                "source_file": "src/graphchat/application/graphs/subgraphs/retrieval_subgraph.py",
                "state_fields": ["planned_action", "retrieval_channel", "retrieval_channels", "retrieval_trace"],
            },
            "retrieve_candidates": {
                "title": "召回候选",
                "description": "按通道并行召回（history/peer/file/web）并记录 trace。",
                "source_file": "src/graphchat/application/graphs/subgraphs/retrieval_subgraph.py",
                "state_fields": ["visible_events", "candidates", "retrieval_trace"],
            },
            "rank_candidates": {
                "title": "候选排序",
                "description": "规则融合评分，生成 focus/support 与改道路由提示。",
                "source_file": "src/graphchat/application/graphs/subgraphs/retrieval_subgraph.py",
                "state_fields": ["focus_reference", "support_references", "reroute_hint", "retrieval_trace"],
            },
        },
    },
    "board_subgraph": {
        "title": "BoardSubgraph",
        "description": "任务板维护子图。",
        "nodes": {
            "board_read": {
                "title": "读取任务板",
                "description": "加载当前任务板快照。",
                "source_file": "src/graphchat/application/graphs/subgraphs/board_subgraph.py",
                "state_fields": ["board_snapshot"],
            },
            "board_update": {
                "title": "更新任务板",
                "description": "执行 upsert/delete/archive/priority/due 操作。",
                "source_file": "src/graphchat/application/graphs/subgraphs/board_subgraph.py",
                "state_fields": ["board_operation", "action_payload"],
            },
            "board_gc": {
                "title": "任务板 GC",
                "description": "按策略清理软删除项（当前由 board_gc 开关触发）。",
                "source_file": "src/graphchat/application/graphs/subgraphs/board_subgraph.py",
                "state_fields": ["board_operation"],
            },
        },
    },
    "governance_subgraph": {
        "title": "GovernanceSubgraph",
        "description": "治理动作子图。",
        "nodes": {
            "governance_prepare": {
                "title": "治理准备",
                "description": "投票/解散群动作载荷标准化。",
                "source_file": "src/graphchat/application/graphs/subgraphs/governance_subgraph.py",
                "state_fields": ["planned_action", "action_payload"],
            },
        },
    },
}
