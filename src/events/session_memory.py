from __future__ import annotations

import asyncio
import json
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from events.references import normalize_references
from events.tagging import (
    extend_tags,
    generate_extra_tags_with_llm,
    generate_extra_tags_with_llm_async,
    generate_tags,
    generate_tags_with_llm_async,
    generate_tags_with_llm,
)
from events.types import Event
from llm.client import LLMRequestOptions


def _stringify_event_content(event: Event) -> str:
    metadata = event.metadata or {}
    sender_name = event.sender_name or metadata.get("sender_name") or metadata.get("name")
    sender_role = event.sender_role or metadata.get("sender_role") or metadata.get("role")
    parts = [
        str(event.type),
        str(event.sender),
        str(sender_name or ""),
        str(sender_role or ""),
        json.dumps(event.content, ensure_ascii=False),
    ]
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
    mapping: Dict[str, Dict[str, Any]]

    @classmethod
    def load(cls, base_dir: Path) -> "TagPool":
        path = base_dir / "tags.json"
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
        else:
            raw = {}
        mapping: Dict[str, Dict[str, Any]] = {}
        for tag, value in raw.items():
            if isinstance(value, dict):
                event_ids = list(value.get("event_ids", []) or [])
                hit_count = int(value.get("hit_count") or 0)
            else:
                event_ids = list(value or [])
                hit_count = 0
            mapping[str(tag)] = {"event_ids": event_ids, "hit_count": hit_count}
        return cls(path=path, mapping=mapping)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["{"]
        items = list(self.mapping.items())
        for idx, (tag, data) in enumerate(items):
            hit_count = 0
            event_ids: List[str] = []
            if isinstance(data, dict):
                hit_count = int(data.get("hit_count") or 0)
                event_ids = list(data.get("event_ids", []) or [])
            else:
                event_ids = list(data or [])
            payload = {"hit_count": hit_count, "event_ids": event_ids}
            line = f"  {json.dumps(str(tag), ensure_ascii=False)}: {json.dumps(payload, ensure_ascii=False, separators=(', ', ': '))}"
            if idx < len(items) - 1:
                line += ","
            lines.append(line)
        lines.append("}")
        self.path.write_text("\n".join(lines), encoding="utf-8")

    def update_from_event(self, event: Event) -> None:
        for tag in event.tags:
            if not tag:
                continue
            bucket = self.mapping.setdefault(
                str(tag), {"event_ids": [], "hit_count": 0}
            )
            event_ids = bucket.setdefault("event_ids", [])
            if event.event_id not in event_ids:
                event_ids.append(event.event_id)

    def list_tags(self) -> List[str]:
        ranking = []
        for tag, data in self.mapping.items():
            hit_count = 0
            if isinstance(data, dict):
                hit_count = int(data.get("hit_count") or 0)
            ranking.append((hit_count, str(tag)))
        ranking.sort(key=lambda item: (item[0], item[1]))
        return [tag for _, tag in ranking]

    def event_ids_for_tags(self, tags: Iterable[str]) -> List[str]:
        event_ids: List[str] = []
        seen = set()
        for tag in tags:
            bucket = self.mapping.get(str(tag), {})
            for event_id in bucket.get("event_ids", []):
                if event_id in seen:
                    continue
                seen.add(event_id)
                event_ids.append(event_id)
        return event_ids

    def record_hits(self, tags: Iterable[str]) -> None:
        lookup = {str(existing).lower(): existing for existing in self.mapping.keys()}
        seen = set()
        for tag in tags:
            if not tag:
                continue
            key = str(tag)
            match = lookup.get(key.lower(), key)
            if match.lower() in seen:
                continue
            seen.add(match.lower())
            bucket = self.mapping.setdefault(match, {"event_ids": [], "hit_count": 0})
            bucket["hit_count"] = int(bucket.get("hit_count") or 0) + 1


@dataclass
class TeamBoard:
    path: Path
    entries: List[Dict[str, Any]]
    window_events: List[str]
    last_boss_event_id: Optional[str] = None

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
            last_boss_event_id=raw.get("last_boss_event_id"),
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "entries": self.entries,
            "window_events": self.window_events,
            "last_boss_event_id": self.last_boss_event_id,
        }
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
        self._maintenance_stopping = False
        self._personal_task_locks: Dict[str, threading.Lock] = {}
        self._tag_pool_lock = threading.Lock()
        self._team_board_lock = threading.Lock()
        if self._maintenance_enabled:
            self._start_maintenance_loop()

    def personal_table_for(self, agent_id: str) -> PersonalTaskTable:
        return PersonalTaskTable.load(agent_id, self.tasks_dir)

    def tag_pool_payload(self) -> Dict[str, Any]:
        return {"tags": self.tag_pool.list_tags(), "index": self.tag_pool.mapping}

    def record_tag_hits(self, tags: Iterable[str]) -> None:
        with self._tag_pool_lock:
            self.tag_pool.record_hits(tags)
            self.tag_pool.save()

    def seed_tag_pool_from_event(self, event: Event, store: Any) -> None:
        if self.tag_pool.mapping:
            return
        content_text = _stringify_event_content(event)
        updated = False
        if not event.tags:
            event.tags = generate_tags_with_llm(
                text=content_text,
                max_tags=6,
                llm_client=self.llm_client,
                llm_mode=self.llm_mode,
            ) or generate_tags(text=content_text, max_tags=6)
            updated = True
        event.tags = self._normalize_selected_tags(event.tags)
        if updated:
            store.update_event(event)
        with self._tag_pool_lock:
            self.tag_pool.update_from_event(event)
            self.tag_pool.save()
        extra_tags = generate_extra_tags_with_llm(
            text=content_text,
            existing_tags=event.tags,
            max_new_tags=3,
            llm_client=self.llm_client,
            llm_mode=self.llm_mode,
        )
        if extra_tags:
            event.tags = extend_tags(event.tags, extra_tags, max_tags=12)
            store.update_event(event)
            with self._tag_pool_lock:
                self.tag_pool.update_from_event(event)
                self.tag_pool.save()

    def team_board_payload(self) -> List[Dict[str, Any]]:
        return list(self.team_board.entries)

    def add_team_board_entry(
        self,
        *,
        summary: str,
        event_ids: Iterable[str],
        kind: str = "summary",
    ) -> None:
        cleaned_ids = [event_id for event_id in event_ids if event_id]
        with self._team_board_lock:
            self.team_board.entries.append(
                {"kind": kind, "summary": summary, "event_ids": cleaned_ids}
            )
            self.team_board.save()

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
        if self._maintenance_stopping:
            self._update_reference_weights(event, store)
            return
        if not self._maintenance_loop or not self._maintenance_queue:
            self._update_reference_weights(event, store)
            return
        try:
            self._maintenance_loop.call_soon_threadsafe(
                self._maintenance_queue.put_nowait, (event, store)
            )
        except RuntimeError:
            self._update_reference_weights(event, store)

    async def _maintenance_worker(self) -> None:
        if not self._maintenance_queue:
            return
        while True:
            item = await self._maintenance_queue.get()
            if item is None:
                self._maintenance_queue.task_done()
                break
            event, store = item
            try:
                await self._run_weight_task(event, store)
            except Exception as exc:  # noqa: BLE001 - ensure background loop lives
                print(f"[events/session_memory.py] ⚠️ 维护任务失败: {type(exc).__name__}: {exc}")
            finally:
                self._maintenance_queue.task_done()

    async def _run_weight_task(self, event: Event, store: Any) -> None:
        await asyncio.to_thread(self._update_reference_weights, event, store)

    async def _run_inline_tasks(self, event: Event, store: Any) -> None:
        await asyncio.gather(
            self._update_personal_tasks_async(event),
            self._update_tags_async(event, store),
            self._update_team_board_async(event, store),
        )

    def _run_inline_sync(self, event: Event, store: Any) -> None:
        self._update_personal_tasks(event)
        self._update_tags(event, store)
        self._update_team_board(event, store)

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

    def _complete(self, messages: List[Dict[str, str]], options: LLMRequestOptions) -> str:
        if self.llm_client is None:
            return ""
        if self.llm_mode == "async":
            return self._run_coroutine_sync(self.llm_client.acomplete(messages, options=options))
        if self.llm_mode == "stream":
            return "".join(self.llm_client.stream(messages, options=options))
        return self.llm_client.complete(messages, options=options)

    def _run_coroutine_sync(self, coro: Any) -> Any:
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

    def handle_event(self, event: Event, store: Any) -> None:
        try:
            self._run_coroutine_sync(self._run_inline_tasks(event, store))
        except Exception as exc:  # noqa: BLE001 - fallback to sync path
            print(f"[events/session_memory.py] ⚠️ 主循环维护任务失败: {type(exc).__name__}: {exc}")
            self._run_inline_sync(event, store)
        if self._maintenance_enabled:
            self._enqueue_maintenance(event, store)
        else:
            self._update_reference_weights(event, store)

    def shutdown(self, timeout: Optional[float] = None) -> bool:
        if not self._maintenance_loop or not self._maintenance_queue:
            return True
        self._maintenance_stopping = True
        drained = self.wait_for_maintenance(timeout=timeout)
        try:
            for _ in range(self._maintenance_workers):
                self._maintenance_loop.call_soon_threadsafe(
                    self._maintenance_queue.put_nowait, None
                )
        except RuntimeError:
            drained = False
        drained = self.wait_for_maintenance(timeout=timeout) and drained
        try:
            self._maintenance_loop.call_soon_threadsafe(self._maintenance_loop.stop)
        except RuntimeError:
            drained = False
        if self._maintenance_thread:
            self._maintenance_thread.join(timeout=timeout)
        return drained

    def _update_personal_tasks(self, event: Event) -> None:
        for agent_id in self._agents.keys():
            self._update_personal_tasks_for_agent(event, agent_id)

    async def _update_personal_tasks_async(self, event: Event) -> None:
        if not self._agents:
            return
        tasks = [
            asyncio.to_thread(self._update_personal_tasks_for_agent, event, agent_id)
            for agent_id in self._agents.keys()
        ]
        if tasks:
            await asyncio.gather(*tasks)

    def _update_personal_tasks_for_agent(self, event: Event, agent_id: str) -> None:
        lock = self._personal_task_locks.get(agent_id)
        if lock is None:
            lock = threading.Lock()
            self._personal_task_locks[agent_id] = lock
        with lock:
            table = self.personal_table_for(agent_id)
            if event.sender == agent_id:
                table.move_todos_to_done(event)
                table.add_done([event.event_id], self._summarize_event_for_tasks(event), memory=False)
                table.compact_done_list()
            table.save()

    def _update_tags(self, event: Event, store: Any) -> None:
        content_text = _stringify_event_content(event)
        updated = False
        seeded = self._seed_tag_pool_if_empty(event, content_text, store)
        updated = updated or seeded
        normalized = self._normalize_selected_tags(event.tags)
        if normalized != event.tags:
            event.tags = normalized
            updated = True

        with self._tag_pool_lock:
            if updated:
                store.update_event(event)
            self.tag_pool.update_from_event(event)
            self.tag_pool.save()

        extra_tags = generate_extra_tags_with_llm(
            text=content_text,
            existing_tags=event.tags,
            max_new_tags=3,
            llm_client=self.llm_client,
            llm_mode=self.llm_mode,
        )
        if extra_tags:
            event.tags = extend_tags(event.tags, extra_tags, max_tags=12)
            with self._tag_pool_lock:
                store.update_event(event)
                self.tag_pool.update_from_event(event)
                self.tag_pool.save()

    async def _update_tags_async(self, event: Event, store: Any) -> None:
        content_text = _stringify_event_content(event)
        updated = False
        seeded = await self._seed_tag_pool_if_empty_async(event, content_text, store)
        updated = updated or seeded
        normalized = self._normalize_selected_tags(event.tags)
        if normalized != event.tags:
            event.tags = normalized
            updated = True

        with self._tag_pool_lock:
            if updated:
                store.update_event(event)
            self.tag_pool.update_from_event(event)
            self.tag_pool.save()

        extra_tags: List[str] = []
        if self.llm_client is not None:
            extra_tags = await generate_extra_tags_with_llm_async(
                text=content_text,
                existing_tags=event.tags,
                max_new_tags=3,
                llm_client=self.llm_client,
                semaphore=self._llm_semaphore,
            )
        else:
            extra_tags = generate_extra_tags_with_llm(
                text=content_text,
                existing_tags=event.tags,
                max_new_tags=3,
                llm_client=None,
                llm_mode=self.llm_mode,
            )
        if extra_tags:
            event.tags = extend_tags(event.tags, extra_tags, max_tags=12)
            with self._tag_pool_lock:
                store.update_event(event)
                self.tag_pool.update_from_event(event)
                self.tag_pool.save()

    @staticmethod
    def _normalize_selected_tags(tags: Iterable[str], max_tags: int = 9) -> List[str]:
        normalized: List[str] = []
        seen = set()
        for tag in tags or []:
            if not tag:
                continue
            key = str(tag).lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(str(tag))
            if len(normalized) >= max_tags:
                break
        return normalized

    def _seed_tag_pool_if_empty(self, event: Event, content_text: str, store: Any) -> bool:
        if self.tag_pool.mapping or event.tags:
            return False
        seed_tags = generate_tags_with_llm(
            text=content_text,
            max_tags=6,
            llm_client=self.llm_client,
            llm_mode=self.llm_mode,
        ) or generate_tags(text=content_text, max_tags=6)
        if not seed_tags:
            return False
        event.tags = self._normalize_selected_tags(seed_tags)
        with self._tag_pool_lock:
            store.update_event(event)
            self.tag_pool.update_from_event(event)
            self.tag_pool.save()
        return True

    async def _seed_tag_pool_if_empty_async(
        self, event: Event, content_text: str, store: Any
    ) -> bool:
        if self.tag_pool.mapping or event.tags:
            return False
        seed_tags = None
        if self.llm_client is not None:
            seed_tags = await generate_tags_with_llm_async(
                text=content_text,
                max_tags=6,
                llm_client=self.llm_client,
                semaphore=self._llm_semaphore,
            )
        if seed_tags is None:
            seed_tags = generate_tags(text=content_text, max_tags=6)
        if not seed_tags:
            return False
        event.tags = self._normalize_selected_tags(seed_tags)
        with self._tag_pool_lock:
            store.update_event(event)
            self.tag_pool.update_from_event(event)
            self.tag_pool.save()
        return True

    def _update_team_board(self, event: Event, store: Any) -> None:
        if not self._is_boss_event(event):
            return
        events = self._collect_team_board_events(event, store)
        seed_prefix = not events
        summary_events = events if events else [event]
        summary = self._summarize_team_board(summary_events, seed_prefix=seed_prefix)
        event_ids = [ev.event_id for ev in summary_events if ev]
        with self._team_board_lock:
            self.team_board.entries.append(
                {"kind": "boss", "summary": summary, "event_ids": event_ids}
            )
            self.team_board.last_boss_event_id = event.event_id
            self.team_board.save()

    def _update_reference_weights(self, event: Event, store: Any) -> None:
        if not event.references:
            return
        normalized = normalize_references(event.references)
        if normalized == event.references:
            return
        event.references = normalized
        store.update_event(event)

    async def _update_team_board_async(self, event: Event, store: Any) -> None:
        if not self._is_boss_event(event):
            return
        events = self._collect_team_board_events(event, store)
        seed_prefix = not events
        summary_events = events if events else [event]
        summary = await self._summarize_team_board_async(summary_events, seed_prefix=seed_prefix)
        event_ids = [ev.event_id for ev in summary_events if ev]
        with self._team_board_lock:
            self.team_board.entries.append(
                {"kind": "boss", "summary": summary, "event_ids": event_ids}
            )
            self.team_board.last_boss_event_id = event.event_id
            self.team_board.save()

    def _is_boss_event(self, event: Event) -> bool:
        return str(event.sender).upper() == "BOSS" or str(event.sender) == "0"

    def _summarize_event(self, event: Event) -> str:
        llm_summary = self._summarize_event_with_llm(event)
        if llm_summary:
            return llm_summary
        content = event.content or {}
        if isinstance(content, dict):
            for key in ("text", "content", "message"):
                if key in content and content[key]:
                    return str(content[key])
        return json.dumps(content, ensure_ascii=False)

    async def _summarize_event_async(self, event: Event) -> str:
        llm_summary = await self._summarize_event_with_llm_async(event)
        if llm_summary:
            return llm_summary
        content = event.content or {}
        if isinstance(content, dict):
            for key in ("text", "content", "message"):
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

    def _collect_team_board_events(self, event: Event, store: Any) -> List[Event]:
        if store is None:
            return []
        try:
            events = store.all()
        except Exception as exc:  # noqa: BLE001 - best-effort
            print(
                f"[events/session_memory.py] ⚠️ 读取事件失败，TeamBoard 仅记录当前事件：{type(exc).__name__}:{exc}"
            )
            return []
        start_index = 0
        if self.team_board.last_boss_event_id:
            for idx, ev in enumerate(events):
                if ev.event_id == self.team_board.last_boss_event_id:
                    start_index = idx + 1
                    break
        end_index = len(events)
        for idx, ev in enumerate(events):
            if ev.event_id == event.event_id:
                end_index = idx
                break
        if end_index < start_index:
            return []
        return events[start_index:end_index]

    def _summarize_team_board(self, events: List[Event], *, seed_prefix: bool) -> str:
        summary = self._summarize_team_board_with_llm(events) or self._summarize_team_board_fallback(events)
        summary = self._compact_summary(summary, max_len=120)
        if seed_prefix:
            return f"本次对话的出发点是：{summary}"
        return summary

    async def _summarize_team_board_async(self, events: List[Event], *, seed_prefix: bool) -> str:
        summary = await self._summarize_team_board_with_llm_async(events)
        if not summary:
            summary = self._summarize_team_board_fallback(events)
        summary = self._compact_summary(summary, max_len=120)
        if seed_prefix:
            return f"本次对话的出发点是：{summary}"
        return summary

    def _summarize_team_board_with_llm(self, events: List[Event]) -> Optional[str]:
        if self.llm_client is None:
            return None
        payloads = [self._team_board_event_payload(ev) for ev in events if ev]
        if not payloads:
            return None
        prompt = (
            "请根据事件列表，用“谁做了什么”的句式总结为一句话。"
            "尽量简短，不使用修饰词。\n"
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
        return summary

    async def _summarize_team_board_with_llm_async(self, events: List[Event]) -> Optional[str]:
        if self.llm_client is None:
            return None
        payloads = [self._team_board_event_payload(ev) for ev in events if ev]
        if not payloads:
            return None
        prompt = (
            "请根据事件列表，用“谁做了什么”的句式总结为一句话。"
            "尽量简短，不使用修饰词。\n"
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
        return summary

    def _summarize_team_board_fallback(self, events: List[Event]) -> str:
        parts = []
        for ev in events:
            sender = self._format_sender_label(ev)
            text = self._extract_event_text(ev)
            if sender and text:
                parts.append(f"{sender}：{text}")
            elif text:
                parts.append(text)
            elif sender:
                parts.append(sender)
        return "；".join(parts) if parts else ""

    @staticmethod
    def _extract_event_text(event: Event) -> str:
        content = event.content or {}
        if isinstance(content, dict):
            for key in ("text", "content", "message"):
                if key in content and content[key]:
                    return str(content[key])
        return json.dumps(content, ensure_ascii=False)

    @staticmethod
    def _format_sender_label(event: Event) -> str:
        metadata = event.metadata or {}
        sender_id = str(event.sender or "")
        sender_name = event.sender_name or metadata.get("sender_name") or metadata.get("name")
        sender_role = event.sender_role or metadata.get("sender_role") or metadata.get("role")
        parts = [sender_id, sender_name, sender_role]
        return ", ".join(str(part) for part in parts if part)

    def _team_board_event_payload(self, event: Event) -> Dict[str, Any]:
        return {
            "sender": self._format_sender_label(event),
            "content": event.content,
            "tags": list(event.tags or []),
        }

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
