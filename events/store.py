import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from .references import normalize_references
from .types import Event


class EventStore:
    def __init__(
        self,
        *,
        base_dir: str = "data/sessions",
        session_id: Optional[str] = None,
        resume: bool = False,
        metadata: Optional[Dict] = None,
    ):
        """可落盘的事件仓库。

        - 默认新建 session：目录 data/sessions/<session_id>/
        - resume=True 且提供 session_id 时，继续往已有 events.jsonl 追加
        """

        self._index: Dict[str, Dict] = {}
        self._events_cache: Optional[List[Event]] = None

        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        if resume:
            if not session_id:
                raise ValueError("resume 模式必须指定 session_id")
            self.session_id = session_id
        else:
            self.session_id = session_id or self._generate_session_id()

        self.session_dir = self.base_dir / self.session_id
        if not resume:
            if self.session_dir.exists():
                if session_id:
                    raise FileExistsError(
                        f"session {self.session_id} 已存在，若要继续请使用 resume 模式"
                    )
                # 避免覆盖历史 session
                while self.session_dir.exists():
                    self.session_id = self._generate_session_id()
                    self.session_dir = self.base_dir / self.session_id
            self.session_dir.mkdir(parents=True, exist_ok=True)

        if resume and not self.session_dir.exists():
            raise FileNotFoundError(f"session {self.session_id} 不存在，无法 resume")

        self.events_path = self.session_dir / "events.jsonl"
        self.index_path = self.session_dir / "index.json"
        self.meta_path = self.session_dir / "meta.json"

        if resume:
            self._load_meta(metadata)
            self._load_index()
        else:
            self._write_meta(metadata)
            self._load_index()

        print(
            f"[events/store.py] 🗂️ session={self.session_id} 就绪，目录 {self.session_dir}。",
        )

    def append(self, event: Event) -> None:
        try:
            event.references = normalize_references(getattr(event, "references", []) or [])
        except Exception:
            pass

        offset, length = self._append_event_to_file(event)
        self._index[event.event_id] = self._index_entry(event, offset, length)
        self._persist_index()

        if self._events_cache is not None:
            self._events_cache.append(event)
        print(
            f"[events/store.py] 🗃️ 收纳事件 {event.event_id}，类型 {event.type}。",
        )

    def get(self, event_id: str) -> Optional[Event]:
        meta = self._index.get(event_id)
        if not meta:
            print(
                f"[events/store.py] ⚠️ 未在索引中找到事件 {event_id}，返回 None。"
            )
            return None

        return self._read_event(meta["offset"], meta["len"])

    def all(self) -> List[Event]:
        if self._events_cache is None:
            self._events_cache = self._load_all_events()
        return list(self._events_cache)

    # ---------- persistence helpers ----------
    @staticmethod
    def _generate_session_id() -> str:
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
        return f"{ts}__{uuid4().hex[:8]}"

    def _write_meta(self, metadata: Optional[Dict]) -> None:
        meta = metadata.copy() if metadata else {}
        meta.setdefault("session_id", self.session_id)
        meta.setdefault("created_at", datetime.now(UTC).isoformat())
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        with self.meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def _load_meta(self, extra_metadata: Optional[Dict]) -> None:
        meta = {}
        if self.meta_path.exists():
            with self.meta_path.open("r", encoding="utf-8") as f:
                meta = json.load(f)
        if extra_metadata:
            meta.update(extra_metadata)
        meta.setdefault("session_id", self.session_id)
        meta["resumed_at"] = datetime.now(UTC).isoformat()
        with self.meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def _append_event_to_file(self, event: Event) -> tuple[int, int]:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(asdict(event), ensure_ascii=False) + "\n"
        data = payload.encode("utf-8")

        with self.events_path.open("ab") as f:
            offset = f.tell()
            f.write(data)

        return offset, len(data)

    def _read_event(self, offset: int, length: int) -> Optional[Event]:
        if not self.events_path.exists():
            print("[events/store.py] ⚠️ events.jsonl 不存在，无法读取事件。")
            return None

        with self.events_path.open("rb") as f:
            f.seek(offset)
            raw = f.read(length)
            if not raw:
                raw = f.readline()
        if not raw:
            print(
                f"[events/store.py] ⚠️ 在 offset={offset} length={length} 未读取到事件数据，返回 None。"
            )
            return None
        data = json.loads(raw.decode("utf-8"))
        return Event(**data)

    def _load_all_events(self) -> List[Event]:
        events: List[Event] = []
        if not self.events_path.exists():
            print("[events/store.py] ⚠️ events.jsonl 不存在，返回空的事件列表。")
            return events

        with self.events_path.open("rb") as f:
            while True:
                offset = f.tell()
                line = f.readline()
                if not line:
                    break
                try:
                    event = Event(**json.loads(line.decode("utf-8")))
                except Exception as exc:
                    print(
                        f"[events/store.py] ⚠️ 无法解析 offset={offset} 的事件：{type(exc).__name__}:{exc}，已跳过。"
                    )
                    continue
                self._index[event.event_id] = self._index_entry(event, offset, len(line))
                events.append(event)

        self._persist_index()
        return events

    def _load_index(self) -> None:
        if self.index_path.exists():
            try:
                self._index = json.loads(self.index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                print("[events/store.py] ⚠️ index.json 解析失败，将尝试重建索引。")
                self._index = {}

        if not self._index and self.events_path.exists():
            print("[events/store.py] ♻️ 未找到有效索引，正在从 events.jsonl 重建 index。")
            self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._index = {}
        if not self.events_path.exists():
            print("[events/store.py] ⚠️ 无法重建索引：events.jsonl 不存在。")
            return

        with self.events_path.open("rb") as f:
            while True:
                offset = f.tell()
                line = f.readline()
                if not line:
                    break
                try:
                    event = json.loads(line.decode("utf-8"))
                    eid = event.get("event_id")
                    if not eid:
                        print(
                            f"[events/store.py] ⚠️ offset={offset} 的事件缺少 event_id，无法索引，已忽略。"
                        )
                        continue
                    self._index[eid] = self._index_entry(event, offset, len(line))
                except Exception as exc:
                    print(
                        f"[events/store.py] ⚠️ 解析 offset={offset} 时出错：{type(exc).__name__}:{exc}，跳过该行。"
                    )
                    continue
        self._persist_index()

    def _persist_index(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps(self._index, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _index_entry(event: Dict | Event, offset: int, length: int) -> Dict:
        def _as_dict(ev: Dict | Event) -> Dict:
            return ev if isinstance(ev, dict) else asdict(ev)

        data = _as_dict(event)
        return {
            "offset": offset,
            "len": length,
            "type": data.get("type"),
            "timestamp": data.get("timestamp"),
            "sender": data.get("sender"),
            "scope": data.get("scope"),
        }