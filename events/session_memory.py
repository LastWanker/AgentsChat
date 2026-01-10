from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from events.references import default_ref_weight, normalize_references
from events.tagging import extend_tags, generate_tags
from events.types import Event
from llm.client import LLMRequestOptions


def _stringify_event_content(event: Event) -> str:
    parts = [str(event.type), str(event.sender), json.dumps(event.content, ensure_ascii=False)]
    return " ".join(part for part in parts if part)


@dataclass
class PersonalTaskTable:
    agent_id: str
    path: Path
    done_list: List[Dict[str, Any]]
    todo_list: List[Dict[str, Any]]

    @classmethod
    def load(cls, agent_id: str, base_dir: Path) -> "PersonalTaskTable":
        path = base_dir / f"{agent_id}.json"
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
        else:
            raw = {}
        return cls(
            agent_id=agent_id,
            path=path,
            done_list=list(raw.get("done_list", []) or []),
            todo_list=list(raw.get("todo_list", []) or []),
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"done_list": self.done_list, "todo_list": self.todo_list}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_todo(self, source_agent_id: str, event_id: str, summary: str) -> None:
        self.todo_list.append(
            {
                "source_agent_id": source_agent_id,
                "event_id": event_id,
                "summary": summary,
            }
        )

    def add_done(self, event_ids: List[str], summary: str, memory: bool = False) -> None:
        self.done_list.append(
            {
                "memory": memory,
                "source_agent_id": self.agent_id,
                "event_ids": event_ids,
                "summary": summary,
            }
        )

    def move_todos_to_done(self, event: Event) -> None:
        if not self.todo_list:
            return
        ref_ids = {ref.get("event_id") for ref in normalize_references(event.references)}
        completed: List[Dict[str, Any]] = []
        remaining: List[Dict[str, Any]] = []
        for item in self.todo_list:
            if item.get("event_id") in ref_ids:
                completed.append(item)
            else:
                remaining.append(item)
        if completed:
            for item in completed:
                summary = f"完成了与事件 {item.get('event_id')} 相关的任务：{item.get('summary')}"
                self.add_done([item.get("event_id")], summary, memory=False)
        self.todo_list = remaining

    def compact_done_list(self) -> None:
        candidates = [item for item in self.done_list if not item.get("memory")]
        if len(candidates) < 9:
            return
        batch = candidates[:3]
        merged_ids: List[str] = []
        summaries: List[str] = []
        for item in batch:
            merged_ids.extend(item.get("event_ids", []))
            summaries.append(item.get("summary", ""))
        merged_summary = "归纳：" + "；".join(summaries)
        self.done_list = [item for item in self.done_list if item not in batch]
        self.add_done(merged_ids[:3], merged_summary, memory=True)


@dataclass
class TagPool:
    path: Path
    mapping: Dict[str, List[str]]

    @classmethod
    def load(cls, base_dir: Path) -> "TagPool":
        path = base_dir / "tags.json"
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
        else:
            raw = {}
        return cls(path=path, mapping={k: list(v) for k, v in raw.items()})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.mapping, ensure_ascii=False, indent=2), encoding="utf-8")

    def update_from_event(self, event: Event) -> None:
        for tag in event.tags:
            if not tag:
                continue
            bucket = self.mapping.setdefault(tag, [])
            if event.event_id not in bucket:
                bucket.append(event.event_id)

    def list_tags(self) -> List[str]:
        return list(self.mapping.keys())

    def event_ids_for_tags(self, tags: Iterable[str]) -> List[str]:
        event_ids: List[str] = []
        seen = set()
        for tag in tags:
            for event_id in self.mapping.get(tag, []):
                if event_id in seen:
                    continue
                seen.add(event_id)
                event_ids.append(event_id)
        return event_ids


@dataclass
class TeamBoard:
    path: Path
    entries: List[Dict[str, Any]]
    window_events: List[str]

    @classmethod
    def load(cls, base_dir: Path) -> "TeamBoard":
        path = base_dir / "team_board.json"
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
        else:
            raw = {}
        return cls(
            path=path,
            entries=list(raw.get("entries", []) or []),
            window_events=list(raw.get("window_events", []) or []),
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"entries": self.entries, "window_events": self.window_events}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def update(self, event: Event, summary: str, *, kind: str) -> None:
        self.entries.append({"kind": kind, "summary": summary, "event_ids": [event.event_id]})


class SessionMemory:
    def __init__(
        self,
        *,
        base_dir: Path,
        agents: List[Any],
        llm_client: Optional[Any] = None,
        llm_mode: str = "sync",
    ) -> None:
        self.base_dir = base_dir
        self.tasks_dir = base_dir / "personal_tasks"
        self.tag_pool = TagPool.load(base_dir)
        self.team_board = TeamBoard.load(base_dir)
        self.llm_client = llm_client
        self.llm_mode = llm_mode
        self._agents = {getattr(agent, "id"): agent for agent in agents}

    def personal_table_for(self, agent_id: str) -> PersonalTaskTable:
        return PersonalTaskTable.load(agent_id, self.tasks_dir)

    def tag_pool_payload(self) -> Dict[str, Any]:
        return {"tags": self.tag_pool.list_tags(), "index": self.tag_pool.mapping}

    def team_board_payload(self) -> List[Dict[str, Any]]:
        return list(self.team_board.entries)

    def handle_event(self, event: Event, store: Any) -> None:
        self._update_personal_tasks(event)
        self._update_tags(event, store)
        self._update_team_board(event, store)
        self._score_reference_weights(event, store)

    def _update_personal_tasks(self, event: Event) -> None:
        for agent_id in self._agents.keys():
            table = self.personal_table_for(agent_id)
            if event.sender != agent_id:
                if event.type in ("request_anyone", "request_specific", "request_all"):
                    if self._should_add_todo(event, agent_id):
                        summary = self._summarize_event(event)
                        table.add_todo(event.sender, event.event_id, summary)
            if event.sender == agent_id:
                table.move_todos_to_done(event)
                table.add_done([event.event_id], self._summarize_event(event), memory=False)
                table.compact_done_list()
            table.save()

    def _update_tags(self, event: Event, store: Any) -> None:
        if not event.tags:
            event.tags = generate_tags(
                text=_stringify_event_content(event),
                fixed_prefix=[str(event.sender), "general"],
                max_tags=6,
            )
            store.update_event(event)
        if not self.tag_pool.mapping:
            extra = generate_tags(
                text=_stringify_event_content(event),
                fixed_prefix=event.tags,
                max_tags=9,
            )
            event.tags = extend_tags(event.tags, extra, max_tags=9)
            store.update_event(event)
        self.tag_pool.update_from_event(event)
        self.tag_pool.save()

    def _update_team_board(self, event: Event, store: Any) -> None:
        self.team_board.window_events.append(event.event_id)
        summary = self._summarize_event(event)
        if self._is_boss_event(event):
            self.team_board.update(event, summary, kind="boss")
        if len(self.team_board.window_events) >= 6:
            window_ids = list(self.team_board.window_events[:6])
            window_summary = f"最近 6 条事件总结：{summary}"
            self.team_board.entries.append(
                {"kind": "window", "summary": window_summary, "event_ids": window_ids}
            )
            self.team_board.window_events = self.team_board.window_events[6:]
        self.team_board.save()

    def _score_reference_weights(self, event: Event, store: Any) -> None:
        if not event.references:
            return
        if self.llm_client is None:
            return
        updated = False
        new_refs = []
        for ref in normalize_references(event.references):
            ref_event_id = ref.get("event_id")
            ref_event = store.get(ref_event_id) if ref_event_id else None
            if not ref_event:
                new_refs.append(ref)
                continue
            weight = ref.get("weight", {})
            for dim in ("dependency", "inspiration", "stance"):
                score = self._score_dimension(event, ref_event, dim)
                if score is None:
                    continue
                weight[dim] = score
                updated = True
            ref["weight"] = weight
            new_refs.append(ref)
        if updated:
            event.references = normalize_references(new_refs)
            store.update_event(event)

    def _score_dimension(self, event: Event, ref_event: Event, dimension: str) -> Optional[float]:
        rubric = _SCORE_RUBRICS.get(dimension)
        if not rubric:
            return None
        prompt = (
            "你是评分器，只输出一个数字。\n"
            f"维度：{dimension}\n"
            f"量表：{rubric}\n"
            "主体事件：" + _stringify_event_content(event) + "\n"
            "被引用事件：" + _stringify_event_content(ref_event) + "\n"
            "只输出一个数字。"
        )
        options = LLMRequestOptions(temperature=0.0, max_tokens=8)
        messages = [{"role": "system", "content": "你是严谨的评分器。"}, {"role": "user", "content": prompt}]
        content = self._complete(messages, options)
        try:
            return float(str(content).strip())
        except (TypeError, ValueError):
            return None

    def _complete(self, messages: List[Dict[str, str]], options: LLMRequestOptions) -> str:
        if self.llm_client is None:
            return ""
        if self.llm_mode == "async":
            import asyncio

            return asyncio.run(self.llm_client.acomplete(messages, options=options))
        if self.llm_mode == "stream":
            return "".join(self.llm_client.stream(messages, options=options))
        return self.llm_client.complete(messages, options=options)

    def _is_boss_event(self, event: Event) -> bool:
        return str(event.sender).upper() == "BOSS" or str(event.sender) == "0"

    def _should_add_todo(self, event: Event, agent_id: str) -> bool:
        if not self._is_event_visible_to_agent(event, agent_id):
            return False
        recipients = set(event.recipients or [])
        if event.type == "request_specific":
            return agent_id in recipients
        if event.type in ("request_anyone", "request_all"):
            return agent_id != event.sender
        return False

    def _is_event_visible_to_agent(self, event: Event, agent_id: str) -> bool:
        agent = self._agents.get(agent_id)
        if agent is None:
            return False
        event_scope = event.scope
        agent_scope = getattr(agent, "scope", "public")
        if event_scope == "public":
            return True
        if agent_scope == "public":
            return True
        return event_scope == agent_scope

    def _summarize_event(self, event: Event) -> str:
        content = event.content or {}
        if isinstance(content, dict):
            for key in ("text", "result", "request", "score"):
                if key in content and content[key]:
                    return str(content[key])
        return json.dumps(content, ensure_ascii=False)


_SCORE_RUBRICS = {
    "dependency": (
        "0完全无关,0.1似有若无,0.2略微相关,0.3轻度关联,0.4有依赖性,0.5明显依赖,"
        "0.6较强依赖,0.7核心依赖,0.8核心一致,0.9几乎复述,1完全转述"
    ),
    "inspiration": (
        "0毫无启发,0.1似有若无,0.2略微影响,0.3轻度影响,0.4影响思路,0.5贡献明显,"
        "0.6较强影响,0.7核心思路,0.8思路一致,0.9按部就班,1完全遵照"
    ),
    "stance": (
        "-1完全对立,-0.9难以弥合,-0.8核心对立,-0.7核心冲突,-0.6较强否认,-0.5明显否认,"
        "-0.4否认态度,-0.3轻度否认,-0.2略感不对,-0.1将信将疑,0无关对错,0.1难说是错,"
        "0.2勉强认可,0.3轻度认可,0.4大致认可,0.5明确认可,0.6较为赞许,0.7核心相似,"
        "0.8核心一致,0.9几乎一致,1完全一致"
    ),
}
