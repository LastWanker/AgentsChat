import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

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

        self._events: List[Event] = []
        self._by_id: Dict[str, Event] = {}

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
        self.meta_path = self.session_dir / "meta.json"

        if resume:
            self._load_meta(metadata)
            self._load_existing_events()
        else:
            self._write_meta(metadata)

        print(
            f"[events/store.py] 🗂️ session={self.session_id} 就绪，目录 {self.session_dir}。",
        )

    def append(self, event: Event) -> None:
        self._events.append(event)
        self._by_id[event.event_id] = event
        self._append_event_to_file(event)
        print(
            f"[events/store.py] 🗃️ 收纳事件 {event.event_id}，类型 {event.type}，目前库存 {len(self._events)} 条。",
        )

    def get(self, event_id: str) -> Optional[Event]:
        return self._by_id.get(event_id)

    def all(self) -> List[Event]:
        return list(self._events)

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

    def _append_event_to_file(self, event: Event) -> None:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def _load_existing_events(self) -> None:
        if not self.events_path.exists():
            print("[events/store.py] ⚠️ resume 模式下未找到 events.jsonl，视为空会话。")
            return

        with self.events_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                ev = Event(**data)
                self._events.append(ev)
                self._by_id[ev.event_id] = ev
        print(
            f"[events/store.py] ♻️ 从磁盘载入 {len(self._events)} 条历史事件，准备继续追加。",
        )