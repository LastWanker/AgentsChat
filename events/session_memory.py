from __future__ import annotations

import asyncio
import json
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from events.references import default_ref_weight, normalize_references
from events.tagging import (
    extend_tags,
    generate_tags,
    generate_tags_with_llm,
    generate_tags_with_llm_async,
)
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
        maintenance_enabled: bool = True,
        maintenance_workers: int = 2,
        maintenance_llm_concurrency: Optional[int] = None,
    ) -> None:
        self.base_dir = base_dir
        self.tasks_dir = base_dir / "personal_tasks"
        self.tag_pool = TagPool.load(base_dir)
        self.team_board = TeamBoard.load(base_dir)
        self.llm_client = llm_client
        self.llm_mode = llm_mode
        self._agents = {getattr(agent, "id"): agent for agent in agents}
        self._maintenance_enabled = maintenance_enabled
        self._maintenance_workers = max(1, maintenance_workers)
        if maintenance_llm_concurrency is None or maintenance_llm_concurrency <= 0:
            self._maintenance_llm_concurrency = None
        else:
            self._maintenance_llm_concurrency = max(1, maintenance_llm_concurrency)
        self._maintenance_loop: Optional[asyncio.AbstractEventLoop] = None
        self._maintenance_queue: Optional[asyncio.Queue] = None
        self._maintenance_thread: Optional[threading.Thread] = None
        self._llm_semaphore: Optional[asyncio.Semaphore] = None
        self._tag_pool_seeded = False
        if self._maintenance_enabled:
            self._start_maintenance_loop()

    def personal_table_for(self, agent_id: str) -> PersonalTaskTable:
        return PersonalTaskTable.load(agent_id, self.tasks_dir)

    def tag_pool_payload(self) -> Dict[str, Any]:
        return {"tags": self.tag_pool.list_tags(), "index": self.tag_pool.mapping}

    def team_board_payload(self) -> List[Dict[str, Any]]:
        return list(self.team_board.entries)

    def _start_maintenance_loop(self) -> None:
        if self._maintenance_loop is not None:
            return
        ready = threading.Event()

        def _runner() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._maintenance_loop = loop
            self._maintenance_queue = asyncio.Queue()
            if self._maintenance_llm_concurrency is not None:
                self._llm_semaphore = asyncio.Semaphore(self._maintenance_llm_concurrency)
            for _ in range(self._maintenance_workers):
                loop.create_task(self._maintenance_worker())
            ready.set()
            loop.run_forever()

        self._maintenance_thread = threading.Thread(target=_runner, daemon=True)
        self._maintenance_thread.start()
        ready.wait(timeout=1)

    def _enqueue_maintenance(self, event: Event, store: Any) -> None:
        if not self._maintenance_loop or not self._maintenance_queue:
            self._run_maintenance_sync(event, store)
            return
        try:
            self._maintenance_loop.call_soon_threadsafe(
                self._maintenance_queue.put_nowait, (event, store)
            )
        except RuntimeError:
            self._run_maintenance_sync(event, store)

    async def _maintenance_worker(self) -> None:
        if not self._maintenance_queue:
            return
        while True:
            event, store = await self._maintenance_queue.get()
            try:
                await self._run_maintenance_tasks(event, store)
            except Exception as exc:  # noqa: BLE001 - ensure background loop lives
                print(f"[events/session_memory.py] ⚠️ 维护任务失败: {type(exc).__name__}: {exc}")
            finally:
                self._maintenance_queue.task_done()

    async def _run_maintenance_tasks(self, event: Event, store: Any) -> None:
        await asyncio.gather(
            self._update_tags_async(event, store),
            self._update_team_board_async(event, store),
            self._score_reference_weights_async(event, store),
        )

    def _run_maintenance_sync(self, event: Event, store: Any) -> None:
        self._update_tags(event, store)
        self._update_team_board(event, store)
        self._score_reference_weights(event, store)

    def wait_for_maintenance(self, timeout: Optional[float] = None) -> bool:
        if not self._maintenance_loop or not self._maintenance_queue:
            return True
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._maintenance_queue.join(), self._maintenance_loop
            )
            future.result(timeout=timeout)
            return True
        except Exception as exc:  # noqa: BLE001 - best-effort drain
            print(f"[events/session_memory.py] ⚠️ 等待维护任务失败: {type(exc).__name__}: {exc}")
            return False

    @asynccontextmanager
    async def _llm_guard(self) -> Any:
        if self._llm_semaphore is None:
            yield
            return
        async with self._llm_semaphore:
            yield

    async def _complete_async(
        self, messages: List[Dict[str, str]], options: LLMRequestOptions
    ) -> str:
        if self.llm_client is None:
            return ""
        if self.llm_mode == "async":
            async with self._llm_guard():
                return await self.llm_client.acomplete(messages, options=options)
        return await asyncio.to_thread(self._complete, messages, options)

    def handle_event(self, event: Event, store: Any) -> None:
        self._update_personal_tasks(event)
        if self._maintenance_enabled:
            self._enqueue_maintenance(event, store)
        else:
            self._run_maintenance_sync(event, store)

    def _update_personal_tasks(self, event: Event) -> None:
        for agent_id in self._agents.keys():
            table = self.personal_table_for(agent_id)
            if event.sender != agent_id:
                if event.type in ("request_anyone", "request_specific", "request_all"):
                    if self._should_add_todo(event, agent_id):
                        summary = self._summarize_event_for_tasks(event)
                        table.add_todo(event.sender, event.event_id, summary)
            if event.sender == agent_id:
                table.move_todos_to_done(event)
                table.add_done([event.event_id], self._summarize_event_for_tasks(event), memory=False)
                table.compact_done_list()
            table.save()

    def _update_tags(self, event: Event, store: Any) -> None:
        content_text = _stringify_event_content(event)
        base_prefix = [str(event.sender), "general"]
        tag_pool_payload = self.tag_pool_payload()
        updated = False

        llm_tags = generate_tags_with_llm(
            text=content_text,
            fixed_prefix=base_prefix,
            max_tags=6,
            llm_client=self.llm_client,
            llm_mode=self.llm_mode,
            tag_pool=tag_pool_payload,
        )
        if llm_tags:
            if llm_tags != event.tags:
                event.tags = llm_tags
                updated = True
        elif not event.tags:
            event.tags = generate_tags(
                text=content_text,
                fixed_prefix=base_prefix,
                max_tags=6,
            )
            updated = True

        if not self.tag_pool.mapping and not self._tag_pool_seeded:
            self._tag_pool_seeded = True
            extra = generate_tags_with_llm(
                text=content_text,
                fixed_prefix=event.tags,
                max_tags=9,
                llm_client=self.llm_client,
                llm_mode=self.llm_mode,
                tag_pool=tag_pool_payload,
            )
            if not extra:
                extra = generate_tags(
                    text=content_text,
                    fixed_prefix=event.tags,
                    max_tags=9,
                )
            event.tags = extend_tags(event.tags, extra, max_tags=9)
            updated = True

        if updated:
            store.update_event(event)
        self.tag_pool.update_from_event(event)
        self.tag_pool.save()

    async def _update_tags_async(self, event: Event, store: Any) -> None:
        content_text = _stringify_event_content(event)
        base_prefix = [str(event.sender), "general"]
        tag_pool_payload = self.tag_pool_payload()
        updated = False

        llm_tags = None
        if self.llm_client is not None:
            if self.llm_mode == "async":
                llm_tags = await generate_tags_with_llm_async(
                    text=content_text,
                    fixed_prefix=base_prefix,
                    max_tags=6,
                    llm_client=self.llm_client,
                    tag_pool=tag_pool_payload,
                    semaphore=self._llm_semaphore,
                )
            else:
                llm_tags = await asyncio.to_thread(
                    generate_tags_with_llm,
                    text=content_text,
                    fixed_prefix=base_prefix,
                    max_tags=6,
                    llm_client=self.llm_client,
                    llm_mode=self.llm_mode,
                    tag_pool=tag_pool_payload,
                )
        if llm_tags:
            if llm_tags != event.tags:
                event.tags = llm_tags
                updated = True
        elif not event.tags:
            event.tags = generate_tags(
                text=content_text,
                fixed_prefix=base_prefix,
                max_tags=6,
            )
            updated = True

        if not self.tag_pool.mapping and not self._tag_pool_seeded:
            self._tag_pool_seeded = True
            extra = None
            if self.llm_client is not None:
                if self.llm_mode == "async":
                    extra = await generate_tags_with_llm_async(
                        text=content_text,
                        fixed_prefix=event.tags,
                        max_tags=9,
                        llm_client=self.llm_client,
                        tag_pool=tag_pool_payload,
                        semaphore=self._llm_semaphore,
                    )
                else:
                    extra = await asyncio.to_thread(
                        generate_tags_with_llm,
                        text=content_text,
                        fixed_prefix=event.tags,
                        max_tags=9,
                        llm_client=self.llm_client,
                        llm_mode=self.llm_mode,
                        tag_pool=tag_pool_payload,
                    )
            if not extra:
                extra = generate_tags(
                    text=content_text,
                    fixed_prefix=event.tags,
                    max_tags=9,
                )
            event.tags = extend_tags(event.tags, extra, max_tags=9)
            updated = True

        if updated:
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
            window_summary = self._summarize_window(window_ids, store) or f"最近 6 条事件总结：{summary}"
            self.team_board.entries.append(
                {"kind": "window", "summary": window_summary, "event_ids": window_ids}
            )
            self.team_board.window_events = self.team_board.window_events[6:]
        self.team_board.save()

    async def _update_team_board_async(self, event: Event, store: Any) -> None:
        self.team_board.window_events.append(event.event_id)
        summary = await self._summarize_event_async(event)
        if self._is_boss_event(event):
            self.team_board.update(event, summary, kind="boss")
        if len(self.team_board.window_events) >= 6:
            window_ids = list(self.team_board.window_events[:6])
            window_summary = await self._summarize_window_async(window_ids, store)
            if not window_summary:
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
        refs = normalize_references(event.references)
        if self.llm_mode == "async":
            updated, refs = self._run_coroutine_sync(
                self._score_reference_weights_async_for_refs(event, refs, store)
            )
        else:
            updated, refs = self._score_reference_weights_sync(event, refs, store)
        if updated:
            event.references = normalize_references(refs)
            store.update_event(event)

    async def _score_reference_weights_async(self, event: Event, store: Any) -> None:
        if not event.references:
            return
        if self.llm_client is None:
            return
        refs = normalize_references(event.references)
        if self.llm_mode == "async":
            updated, refs = await self._score_reference_weights_async_for_refs(event, refs, store)
        else:
            updated, refs = await asyncio.to_thread(
                self._score_reference_weights_sync, event, refs, store
            )
        if updated:
            event.references = normalize_references(refs)
            store.update_event(event)

    def _score_reference_weights_sync(
        self, event: Event, refs: List[Dict[str, Any]], store: Any
    ) -> tuple[bool, List[Dict[str, Any]]]:
        updated = False
        new_refs: List[Dict[str, Any]] = []
        for ref in refs:
            ref_event_id = ref.get("event_id")
            ref_event = store.get(ref_event_id) if ref_event_id else None
            if not ref_event:
                new_refs.append(ref)
                continue
            weight = dict(ref.get("weight", {}) or {})
            for dim in ("dependency", "inspiration", "stance"):
                score = self._score_dimension(event, ref_event, dim)
                if score is None:
                    continue
                weight[dim] = score
                updated = True
            ref["weight"] = weight
            new_refs.append(ref)
        return updated, new_refs

    async def _score_reference_weights_async_for_refs(
        self, event: Event, refs: List[Dict[str, Any]], store: Any
    ) -> tuple[bool, List[Dict[str, Any]]]:
        tasks = []
        meta: List[tuple[int, str]] = []
        for idx, ref in enumerate(refs):
            ref_event_id = ref.get("event_id")
            ref_event = store.get(ref_event_id) if ref_event_id else None
            if not ref_event:
                continue
            for dim in ("dependency", "inspiration", "stance"):
                tasks.append(self._score_dimension_async(event, ref_event, dim))
                meta.append((idx, dim))
        if not tasks:
            return False, refs
        results = await self._gather_scores(tasks)
        updated = False
        for (idx, dim), score in zip(meta, results):
            if score is None:
                continue
            weight = dict(refs[idx].get("weight", {}) or {})
            weight[dim] = score
            refs[idx]["weight"] = weight
            updated = True
        return updated, refs

    async def _gather_scores(self, tasks: List[Any]) -> List[Optional[float]]:
        import asyncio

        return await asyncio.gather(*tasks)

    def _run_coroutine_sync(self, coro: Any) -> Any:
        import asyncio
        import threading

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        result: dict[str, Any] = {}
        error: dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                result["value"] = asyncio.run(coro)
            except BaseException as exc:
                error["value"] = exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if "value" in error:
            raise error["value"]
        return result.get("value")

    def _score_dimension(self, event: Event, ref_event: Event, dimension: str) -> Optional[float]:
        rubric = _SCORE_RUBRICS.get(dimension)
        if not rubric:
            return None
        relation_hint = _SCORE_RELATIONS.get(dimension, "")
        prompt = self._score_prompt(event, ref_event, dimension, rubric, relation_hint)
        options = LLMRequestOptions(temperature=0.0, max_tokens=8)
        messages = [{"role": "system", "content": "你是严谨的评分器。"}, {"role": "user", "content": prompt}]
        content = self._complete(messages, options)
        return _parse_score(content)

    async def _score_dimension_async(
        self, event: Event, ref_event: Event, dimension: str
    ) -> Optional[float]:
        rubric = _SCORE_RUBRICS.get(dimension)
        if not rubric:
            return None
        relation_hint = _SCORE_RELATIONS.get(dimension, "")
        prompt = self._score_prompt(event, ref_event, dimension, rubric, relation_hint)
        options = LLMRequestOptions(temperature=0.0, max_tokens=8)
        messages = [{"role": "system", "content": "你是严谨的评分器。"}, {"role": "user", "content": prompt}]
        async with self._llm_guard():
            content = await self.llm_client.acomplete(messages, options=options)
        return _parse_score(content)

    def _score_prompt(
        self,
        event: Event,
        ref_event: Event,
        dimension: str,
        rubric: str,
        relation_hint: str,
    ) -> str:
        return (
            "你是评分器，只输出一个数字。\n"
            f"维度：{dimension}\n"
            f"关系：{relation_hint}\n"
            f"量表：{rubric}\n"
            "主体事件：" + self._brief_event(event) + "\n"
            "被引用事件：" + self._brief_event(ref_event) + "\n"
            "只输出一个数字。"
        )

    def _complete(self, messages: List[Dict[str, str]], options: LLMRequestOptions) -> str:
        if self.llm_client is None:
            return ""
        if self.llm_mode == "async":
            return self._run_coroutine_sync(self.llm_client.acomplete(messages, options=options))
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
        llm_summary = self._summarize_event_with_llm(event)
        if llm_summary:
            return llm_summary
        content = event.content or {}
        if isinstance(content, dict):
            for key in ("text", "result", "request", "score"):
                if key in content and content[key]:
                    return str(content[key])
        return json.dumps(content, ensure_ascii=False)

    async def _summarize_event_async(self, event: Event) -> str:
        llm_summary = await self._summarize_event_with_llm_async(event)
        if llm_summary:
            return llm_summary
        content = event.content or {}
        if isinstance(content, dict):
            for key in ("text", "result", "request", "score"):
                if key in content and content[key]:
                    return str(content[key])
        return json.dumps(content, ensure_ascii=False)

    def _summarize_event_with_llm(self, event: Event) -> Optional[str]:
        if self.llm_client is None:
            return None
        prompt = (
            "请用不超过40字总结事件的核心信息，输出一句话。\n"
            f"事件类型：{event.type}\n"
            f"发送者：{event.sender}\n"
            f"内容：{json.dumps(event.content, ensure_ascii=False)}"
        )
        options = LLMRequestOptions(temperature=0.2, max_tokens=64)
        messages = [
            {"role": "system", "content": "你是事件摘要器。"},
            {"role": "user", "content": prompt},
        ]
        summary = self._complete(messages, options).strip()
        if not summary:
            return None
        return self._compact_summary(summary)

    async def _summarize_event_with_llm_async(self, event: Event) -> Optional[str]:
        if self.llm_client is None:
            return None
        prompt = (
            "请用不超过40字总结事件的核心信息，输出一句话。\n"
            f"事件类型：{event.type}\n"
            f"发送者：{event.sender}\n"
            f"内容：{json.dumps(event.content, ensure_ascii=False)}"
        )
        options = LLMRequestOptions(temperature=0.2, max_tokens=64)
        messages = [
            {"role": "system", "content": "你是事件摘要器。"},
            {"role": "user", "content": prompt},
        ]
        summary = (await self._complete_async(messages, options)).strip()
        if not summary:
            return None
        return self._compact_summary(summary)

    def _summarize_window(self, event_ids: List[str], store: Any) -> Optional[str]:
        if self.llm_client is None:
            return None
        events = [store.get(event_id) for event_id in event_ids]
        payloads = []
        for ev in events:
            if not ev:
                continue
            payloads.append(
                {
                    "event_id": getattr(ev, "event_id", ""),
                    "type": getattr(ev, "type", ""),
                    "sender": getattr(ev, "sender", ""),
                    "content": getattr(ev, "content", {}),
                }
            )
        if not payloads:
            return None
        prompt = (
            "请归纳最近事件的整体进展，不超过60字，输出一句话。\n"
            f"事件列表：{json.dumps(payloads, ensure_ascii=False)}"
        )
        options = LLMRequestOptions(temperature=0.2, max_tokens=80)
        messages = [
            {"role": "system", "content": "你是团队进展摘要器。"},
            {"role": "user", "content": prompt},
        ]
        summary = self._complete(messages, options).strip()
        if not summary:
            return None
        return f"最近 6 条事件总结：{self._compact_summary(summary)}"

    async def _summarize_window_async(self, event_ids: List[str], store: Any) -> Optional[str]:
        if self.llm_client is None:
            return None
        events = [store.get(event_id) for event_id in event_ids]
        payloads = []
        for ev in events:
            if not ev:
                continue
            payloads.append(
                {
                    "event_id": getattr(ev, "event_id", ""),
                    "type": getattr(ev, "type", ""),
                    "sender": getattr(ev, "sender", ""),
                    "content": getattr(ev, "content", {}),
                }
            )
        if not payloads:
            return None
        prompt = (
            "请归纳最近事件的整体进展，不超过60字，输出一句话。\n"
            f"事件列表：{json.dumps(payloads, ensure_ascii=False)}"
        )
        options = LLMRequestOptions(temperature=0.2, max_tokens=80)
        messages = [
            {"role": "system", "content": "你是团队进展摘要器。"},
            {"role": "user", "content": prompt},
        ]
        summary = (await self._complete_async(messages, options)).strip()
        if not summary:
            return None
        return f"最近 6 条事件总结：{self._compact_summary(summary)}"

    def _summarize_event_for_tasks(self, event: Event) -> str:
        summary = self._summarize_event(event)
        summary = self._compact_summary(summary)
        return f"{event.sender}：{summary}" if summary else str(event.sender)

    @staticmethod
    def _compact_summary(text: str, max_len: int = 80) -> str:
        text = str(text).strip()
        if len(text) <= max_len:
            return text
        return text[: max_len - 1] + "…"

    def _brief_event(self, event: Event, max_len: int = 120) -> str:
        summary = self._compact_summary(self._summarize_event(event), max_len=max_len)
        return f"{event.type}/{event.sender}:{summary}"


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

_SCORE_RELATIONS = {
    "dependency": "被引用事件对主体事件的依赖程度",
    "inspiration": "被引用事件对主体事件的启发程度",
    "stance": "主体事件对被引用事件的态度",
}


def _parse_score(content: Any) -> Optional[float]:
    try:
        return float(str(content).strip())
    except (TypeError, ValueError):
        return None
