# agent.py
from uuid import uuid4
from datetime import datetime, UTC
from typing import List, Optional, Dict, Any

# 最后一次修改时间：2026年1月6日 16:23:39

"""
☆agent结构设计思路↓
"""
"""
agent：系统中最小的“社会行动者”
它的唯一职责：以规范化 Event 的形式，对外产生行为。
agent.py只负责标注，不负责解释

agent.py 的核心目标，其实很单纯：把“社会行为”从“实现细节”中剥离出来，并且固定成一种稳定、可追溯、可被解释的数据结构。
我在这里定义的 Agent，并不是“会思考的智能体”，也不是“承担任务的执行者”，而是系统中最小的社会行动者。它唯一需要做的事情，就是：
    当它决定对外行动时，把这个行动规范地记录为一个 Event。
至于这个 Event 之后如何被理解、被评价、被计算，那是系统其他部分（图、归因、分析）的职责，不是 Agent 的职责。

关于 Event 的定位
Event 不是日志，也不是函数调用记录，而是社会意义上的“可见行为”。
只有满足“可见性”的行为，才有资格成为 Event：
    在群里发言是 Event、向另一个 Agent 提交结果是 Event、发起请求、投票、评价、分组声明是 Event；
    Agent 内部调用 LLM、爬虫、计算，不是 Event。
这条界线非常重要，它决定了：系统研究的对象不是“Agent 如何思考”，而是“Agent 如何协作”。

关于 Reference 的设计
Event 之间的关系，不通过上下文、不通过隐式状态，而是显式通过 reference 建立。
☆ ♥♥♥♥♥ Reference 只保留一种结构：带有 event_id 和三维权重（stance / inspiration / dependency）的对象。
这样做的目的不是为了复杂，而是为了保留一个事实：
    很多行为在发生时，并没有被完全定性。
评价、赞同、反对、贡献大小，这些都不必在行为发生当下就被锁死。
Agent 只负责“引用了谁”，至于“这意味着什么”，留给后续系统解释。

关于 completed 的含义
completed 不是“这个行为成功了”，而是：这个社会流程是否已经闭合。
    speak 一旦发生就天然完成
    request、group、state_change 默认未完成，它们需要被 submit、evaluation、后续行为引用，才算闭合
这让 Event 不只是瞬时动作，而是可以被延续、回应、完成的过程节点。

关于 scope 与分组
scope 不是权限系统，而是可见域的声明。
    public：所有 Agent 都能看到
    group：只有组内 Agent 可见
public 永远对所有人开放，包括已经在 group 中的 Agent
join_group / leave_group 的设计刻意分成两步：
    先 public 声明，再改变自身状态。
这保证了一点：世界先被告知，状态才发生变化。

关于 Agent 的克制
Agent 不保存事件本体，只保存 event_id；
    不解释历史，只声明行为；
    不推理因果，只提供引用。
这是刻意的克制，也是为了避免未来系统演化时，Agent 变成一个什么都管、什么都知道、什么都算的“上帝对象”。

总结给自己的一句话：
agent.py 做的不是“把事做完”，而是“把事说清楚”。
只要说清楚，剩下的判断、计算、归因，都可以推迟。
"""
"""
☆agent.py 所有函数的设计细节↓
"""
"""
Agent.__init__
设计思路：
    初始化只做三件事：身份、状态、能力声明。
    不加载上下文、不绑定系统、不注册全局。
    id 使用 uuid，是为了支持销毁 / 重建 / 分布式，不依赖数据库顺序。
    state 和 scope 明确区分：一个是“我在干嘛”，一个是“别人能看到什么”。
    memory 只存 event_id，明确 Agent 不是历史真相的持有者。
    available_events 是显式能力声明，为调度器 / UI / 能力裁剪预留接口。

_new_event
设计思路：
    这是 Agent 的“唯一出口”，所有社会行为最终都要过这里。
    强制 keyword-only 参数，是为了避免调用时语义混乱。
    metadata 中的 forced_scope，是为了把“事件发生时的世界”和“事件之后的世界”分开。
    references 允许是模糊的（str）或加权的，是为了延迟解释。
    completed 不自动推断，交给上层行为明确声明。
预留接口：
    metadata 将来可以挂 rule_id、policy_tag、trace_id
    recipients 为未来私聊 / 定向请求 / 子系统通信预留

speak
设计思路：
    最基础、最频繁的社会行为，在当前 scope 内发言。
    不关心对象、不关心结果
    references 可选，用于“接话”“反驳”“补充”
预留接口：
    references 的权重将来可用于“发言影响力”计算

speak_public
设计思路：
    无条件公共广播，是对 scope 机制的一次“越权但合法”的使用。
    明确使用 forced_scope="public"
    不改变自身状态，只改变可见性
预留接口：
    小组发言人 / 组长的“对外发言”直接复用这个函数

request_specific
设计思路：
    明确点名的请求，必须是 public 的，因为它本身就是一种公开委托。
    completed=False，等待 submit 闭合
    recipients 明确目标，便于后续责任归因
预留接口：
    后续可以加超时、拒绝、转交机制

request_anyone
设计思路：
    广播式求助，不指定对象，但要求后续有人接单。
    public 是默认且必须的
    不要求一定完成，但允许被引用
预留接口：
    可扩展为“悬赏任务”“自愿认领”

request_all
设计思路：
    集体决策的起点，本质是“规则 + 要求”的声明。
    rule 不强制结构，只要求可被理解
    所有人 submit 后，才算真正完成
预留接口：
    投票、打分、排序、共识算法都从这里接入

submit
设计思路：
    交付行为，必须引用 request 类 event，否则没有语义来源。
    public 参数区分“组内交付”和“向公共域/上级交付”
    submit 本身天然 completed
预留接口：
    result 现在是 str，未来可升级为结构化产出

evaluation
设计思路：
    评价是天然带“态度”的行为，因此 reference 自动带权。
    如果只是 event_id，权重自动继承 score
    允许引用多个 event
预留接口：
    权重将来直接进入归因图、贡献度计算

state_change
设计思路：
    这是一个“声明式状态变化”，不是偷偷改变量。
    默认 completed=False，等待引用确认
    forced_scope 允许把状态声明公开
预留接口：
    可统一承载请假、拒绝、忙碌、失能等状态

join_group
设计思路：
    先对公共世界声明，再改变自身状态。
    event 发生在进入 group 之前
    状态变化发生在 event 之后
预留接口：
    group 可以被建模为“类 Agent 实体”
    投票通过后再 join，只是多一个 reference

leave_group
设计思路：
    与 join_group 对称，同样强调“先声明，后变化”。
    leave 本身不代表工作完成
    是否总结，由后续 speak / submit 决定
预留接口：
    leave 后可强制期待一次总结性引用

给未来自己的总备注

这份代码的原则是：
宁可多留结构，不提前下结论；宁可显式声明，不隐式推断。

Agent 不聪明没关系，
只要它说的话、做的事、站的位置，
都能被系统长期理解就够了。
"""


from events.references import default_ref_weight, normalize_references
from events.types import Reference


class Agent:
    def __init__(
            self,
            name: str,
            role: str,
            expertise: List[str],
            priority: float = 0.5,
    ):
        # Agent的系统级唯一身份。潜台词是：Agent 可以被销毁、重建、分布式迁移但 id 不依赖数据库、不依赖顺序、不依赖上下文
        self.id = str(uuid4())

        # 在Agent生命周期内不该频繁变化的属性。
        self.name = name
        self.role = role
        self.expertise = expertise

        # 可以临时投票降低某Agent的优先级，但是大多数时候是事后根据结果的优劣和归因算法调整
        self.priority = priority

        # 状态
        self.state = "idle"

        # 可见区域。这不违反公开性，只是公开域不一样。
        self.scope = "public"  # public | group:<id>

        # memory 只存 event_id，不存 event 本体。Agent 不是历史数据库，它只是“知道自己参与过什么”
        self.memory: List[str] = []  # event_ids

        # 显式声明：Agent“知道”自己能干什么，而且应该是时刻被提醒。
        # 这不是为了 Python，而是为了系统反射能力：
        # 调度器可以问：你能不能 evaluation？
        # UI 可以根据这个生成按钮
        # 后续可以做能力裁剪 / 角色限制
        self.available_events = {
            "speak",
            "speak_public",
            "request_specific",
            "request_anyone",
            "request_all",
            "submit",
            "evaluation",
            "state_change",
        }

    # ---------- 基础工具 ----------
    # Agent.memory 的唯一写入口，是 observe()
    def observe(self, event: dict):
        """
        Agent 看见一个世界事件
        当前版本：只记录，不行动
        """

        event_id = event.get("event_id")
        if event_id:
            self.memory.append(event_id)
            print(
                f"[agents/agent.py] 👁️  Agent {self.name} 记录看到的事件 {event_id}，当前记忆 {len(self.memory)} 条。"
            )

        # self.memory.append({
        #     "seen_event": event["event_id"]
        # })
        # # 现在，要验证的是因果方向是否正确，不是 schema↑ 是否优雅。
        # # 当前这个：{"seen_event": event_id}完全够用，而且它有一个优点：简陋到不可能被误用为事实
        # # 未来我们会真正设计scheme格式，例如下面↓。
        # """
        #         {
        #   "type": "seen_event",
        #   "event_id": "...",
        #   "from": "...",
        #   "timestamp": ...
        # }
        # """

    def _normalize_references(self, references: Optional[List[Reference | str]]) -> List[Reference]:
        """Ensure outgoing references always use the weighted schema."""

        if not references:
            return []
        return normalize_references(references)

    def _new_event(  # “_”表示：这是 Agent 的内部工具，外部不应该直接调用
            self,
            event_type: str,
            content: Dict[str, Any],
            *,  # *,表示一个分隔符，它强制后续的参数必须通过关键字参数（keyword arguments）的方式传递，而不能通过位置参数（positional arguments）传递。
            recipients: Optional[List[str]] = None,
            # references: Optional[List[str]] = None,
            references: Optional[List[Reference | str]] = None,
            metadata: Optional[Dict[str, Any]] = None,
            completed: bool = True,
    ) -> Dict[str, Any]:

        metadata = metadata or {}
        # scope 决定权：显式 forced_scope > 当前 self.scope
        scope = metadata.get("forced_scope", self.scope)

        event = {
            "event_id": str(uuid4()),
            "type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "sender": self.id,

            "recipients": recipients or [],
            "scope": scope,

            "content": content,
            "references": self._normalize_references(references),
            "metadata": metadata,  # or {},

            "completed": completed,
        }

        # Agent 只负责“我做过什么”，不负责“全局发生了什么”。 # 新的变更！统一 memory 的写入口：只允许 observe 写
        # self.memory.append(event["event_id"])  # 写法淘汰。统一 memory 的写入口：只允许 observe 写，详见上面的observe类

        return event

    # ---------- 社会行为 ----------
    # ---------- 发言行为 ----------
    def speak(self, text: str, references: Optional[List[Reference | str]] = None):
        # 在当前 scope 发言
        return self._new_event(
            "speak",
            {"text": text},
            references=references,
        )

    def speak_public(self, text: str, references: Optional[List[Reference | str]] = None):
        # 无条件 public 广播
        return self._new_event(
            "speak_public",
            {"text": text},
            references=references,
            metadata={"forced_scope": "public"},
        )

    # ---------- 请求行为 ----------（一律public）
    def request_specific(self, target_agent_id: str, request: str):
        return self._new_event(
            "request_specific",
            {"request": request},
            recipients=[target_agent_id],
            completed=False,
            metadata={"forced_scope": "public"},
        )

    def request_anyone(self, request: str):
        return self._new_event(
            "request_anyone",
            {"request": request},
            completed=False,
            metadata={"forced_scope": "public"},
        )

    def request_all(self, request: str, rule: Optional[dict] = None):
        return self._new_event(
            "request_all",
            {
                "request": request,
                "rule": rule or {"type": "vote"},
            },
            completed=False,
            metadata={"forced_scope": "public"},
        )

    # ---------- 交付行为 ----------（一律public）
    def submit(
            self,
            result: str,
            references: List[Reference | str],
            public: bool = False,
    ):
        if not references:
            raise ValueError("submit 必须引用至少一个 request 类 event")

        return self._new_event(
            "submit",
            {"result": result},
            references=references,
            completed=True,
            metadata={
                "forced_scope": "public" if public else self.scope
            },
        )

    # ---------- 评价行为 ----------（天然带符号浮点数的权）
    def evaluation(
            self,
            score: float,
            comment: str,
            references: List[Reference | str],
    ):
        weighted_refs: List[Reference] = []

        for ref in self._normalize_references(references):
            weight = default_ref_weight()
            weight.update(ref.get("weight", {}))
            weight["stance"] = score
            weighted_refs.append({"event_id": ref["event_id"], "weight": weight})

        return self._new_event(
            "evaluation",
            {"comment": comment},
            references=weighted_refs,
            completed=True,
        )

    # ---------- 状态变更 ----------（通用）
    def state_change(
            self,
            new_state: str,
            *,
            references: Optional[List[Reference | str]] = None,
            note: Optional[str] = None,
            completed: bool = False,
            forced_scope: Optional[str] = None,
    ):
        return self._new_event(
            "state",
            {
                "state": new_state,
                "note": note,
            },
            references=references,
            completed=completed,
            metadata={
                "forced_scope": forced_scope
            } if forced_scope else None,
        )

    # ---------- 分组行为 ----------

    def join_group(self, group_id: str, references: List[Reference | str]):
        """
        宣告：我将加入某个 group
        - 事件发生在进入 group 之前
        - 事件必须是 public
        - 状态变化发生在事件之后
        """

        event = self.state_change(
            "grouped",
            references=references,
            note=f"join group {group_id}",
            completed=False,
            forced_scope="public",
        )

        # 事件之后，世界才真的改变
        self.state = "grouped"
        self.scope = f"group:{group_id}"

        return event

    def leave_group(self, references: List[Reference | str]):
        """
        宣告：我将离开当前 group
        同样是 public 事件
        """

        event = self.state_change(
            "idle",
            references=references,
            note="leave group",
            completed=False,
            forced_scope="public",
        )

        # 事件之后，回到公共世界
        self.state = "idle"
        self.scope = "public"

        return event
