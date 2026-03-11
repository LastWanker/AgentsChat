# 03 RAG 记忆召回与本地持久化

## 1. 记忆架构分层

不要把“记忆”做成一个超级类，建议拆成四层：

1. 事实层：`EventStore`（append-only 事件日志）。
2. 执行层：LangGraph checkpoint（状态推进上下文）。
3. 语义层：向量/关键词索引（RAG 候选召回）。
4. 归纳层：任务板、摘要、结论（可重建缓存）。

## 2. 本地存储建议（满足“上下文保存在本地”）

### 2.1 事实层（必须）

- `events.jsonl` 或 `events.db(SQLite)`。
- 作为唯一事实源，可重放、可审计。

### 2.2 checkpoint 层（必须）

- 每 Agent 线程独立保存 checkpoint。
- 推荐本地 SQLite checkpointer 或本地 Postgres。
- key 结构：`(session_id, thread_id, checkpoint_ns, checkpoint_id)`。

### 2.3 检索层（建议）

- `event_chunks`：事件文本切片。
- `event_embeddings`：向量索引（本地向量库或 sqlite-vss）。
- `tag_inverted_index`：标签倒排（保留你现有优势）。

## 3. RAG 检索通道设计为“内陷子图”

你说的“先进入一个小图检索，再退出继续主流程”是成立的，建议显式建 `RetrievalSubgraph`。
实现上优先使用 LangGraph 官方子图能力（`use-subgraphs`），避免把子流程写成难维护的分支跳转。

### 3.1 子图入口条件

- 当前动作需要证据（评价、提问、修正、任务决策）。
- 或 `citation_policy != none`。

### 3.2 子图内节点（受控通道）

- `choose_channel_node`：选择通道。
- `world_history_node`：看群内历史（主群/小群/私聊）。
- `ask_peer_node`：请求某人补充信息。
- `web_search_node`：联网查找。
- `file_search_node`：检索共享文件。
- `merge_candidates_node`：合并去重并打标签。

输出结构示例：

```json
{
  "channel": "world_history",
  "query": "海龟汤关键信息",
  "time_window_min": 120,
  "top_k": 8
}
```

### 3.3 子图退出条件

- 候选集达到最小数量 `min_candidates`，返回主图。
- 或超时/无结果，返回“改道建议”（`ask_peer`/`web_search`/`defer`）。

## 4. 引用策略与评分（降低 LLM 打分幻觉）

## 4.1 候选评分：规则可计算优先

建议把分数拆成“可计算特征 + LLM 仅解释”：

```text
value_score =
  0.45 * semantic_sim +
  0.20 * source_weight +
  0.15 * freshness +
  0.10 * dependency_graph +
  0.10 * consensus
```

实现原则：

- `semantic_sim`：向量余弦相似度（可计算）。
- `source_weight`：来源权重表（Boss/系统/人工确认事件更高）。
- `freshness`：时间衰减函数（可计算）。
- `dependency_graph`：事件依赖边距离（可计算）。
- `consensus`：多来源是否一致（可计算）。

LLM 的角色只保留两项：

- 意图分类（例如 `evaluate_claim`、`question_claim`）。
- 生成可读解释（为什么选了这些候选）。

## 4.2 条件化引用规则（不再默认强制唯一主引用）

仅当行为属于“针对某个说法”的场景时，才要求焦点引用：

- `evaluate_claim`
- `question_claim`
- `modify_claim`
- `rebut_claim`

其它场景（闲聊、流程播报、状态同步）允许 `focus_reference = null`。

## 4.3 比“唯一主引用”更稳的结构

建议从“单一主引用”升级到“焦点 + 辅助”：

- `focus_reference`: 0 或 1 个，表示当前行为主要针对的事件。
- `support_references`: 0..N 个，表示补充证据。
- `reference_role`: `focus|support|context|counter`。

这样既保留“可追溯”，又避免强行选一个不合适主引用。

## 4.4 引用守卫节点

`citation_guard_node` 按 `citation_policy` 检查：

- `none`：可无引用。
- `optional`：可有可无，但若给出必须来自候选。
- `required_focus`：必须 1 个 `focus_reference` 且来自候选。

不通过时返回结构化错误，触发重试或改道。

## 5. 任务板/记录板作为一等状态

任务板不是“顺带写在上下文里”，而是独立实体与节点：

- `board_read_node`：读取当前任务板。
- `board_update_node`：新增/更新/删除任务项或记录项。
- `board_link_ref_node`：把板项绑定到事件引用。

建议事件：

- `board_item_upserted`
- `board_item_deleted`
- `board_item_linked_ref`

## 6. 本地数据结构示例

```sql
CREATE TABLE events (
  event_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  world_scope TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  action_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  focus_reference TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE event_refs (
  event_id TEXT NOT NULL,
  ref_event_id TEXT NOT NULL,
  reference_role TEXT NOT NULL,
  value_score REAL NOT NULL
);

CREATE TABLE board_items (
  item_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  owner_id TEXT,
  linked_event_id TEXT,
  updated_at TEXT NOT NULL
);
```

## 7. 检索与事件写入的关系

必须坚持：

- 检索索引是可重建缓存，不是事实源。
- 事实以 EventStore 为准。
- checkpoint 丢失可以恢复；事实丢失不可恢复。

## 8. 记忆漂移控制

为解决“Agent 忘记自己是谁/忘记上下文”：

- 固定 `AgentProfile`（身份、权限、目标）做结构化输入。
- 每轮只喂给模型“最近窗口 + 高价值记忆 + 当前任务上下文 + 当前任务板快照”。
- 周期性摘要事件化（`summary_generated`）并可引用。

## 9. 最小可落地实现顺序

1. 先保留现有 tag 倒排召回 + 条件化 `citation_guard`。
2. 增加 `focus_reference + support_references` 结构。
3. 接入向量召回与规则化评分器（LLM 只做解释）。
4. 落地任务板节点与 `board_items` 持久化。
5. 最后做多通道融合与在线校准。
