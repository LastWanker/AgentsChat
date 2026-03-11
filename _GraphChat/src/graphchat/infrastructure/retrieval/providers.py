from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from graphchat.infrastructure.persistence.event_store import JsonlEventStore


def _token_overlap_ratio(text: str, query: str) -> float:
    q = set(str(query).lower().split())
    t = set(str(text).lower().split())
    if not q or not t:
        return 0.0
    return len(q & t) / max(len(q | t), 1)


class PeerEventSearchProvider:
    """基于本地事件事实库的同伴信息检索。"""

    def __init__(self, event_store: JsonlEventStore):
        self._event_store = event_store

    def search(
        self,
        *,
        session_id: str,
        query: str,
        top_k: int,
        agent_id: str | None = None,
        visible_events: list[dict] | None = None,
    ) -> list[dict]:
        events = list(visible_events or self._event_store.list_events(session_id))
        peer_events = [event for event in events if event.get("actor_id") not in {None, "", agent_id}]
        total = max(len(peer_events), 1)
        rows: list[dict] = []
        for idx, event in enumerate(reversed(peer_events)):
            event_id = str(event.get("event_id", "")).strip()
            if not event_id:
                continue
            text = str(event.get("payload", {}).get("text", ""))
            score = _token_overlap_ratio(text, query)
            rows.append(
                {
                    "event_id": event_id,
                    "semantic_sim": score,
                    "freshness": 1.0 - (idx / total),
                    "dependency_graph": 0.35,
                    "payload": {"text": text, "actor_id": event.get("actor_id")},
                }
            )
        rows.sort(key=lambda x: (x.get("semantic_sim", 0.0), x.get("freshness", 0.0)), reverse=True)
        return rows[:max(top_k, 1)]


class LocalFileSearchProvider:
    """本地文件检索：扫描会话目录下 files/ 的文本文件。"""

    def __init__(self, sessions_dir: Path, max_file_size: int = 256 * 1024):
        self._sessions_dir = sessions_dir
        self._max_file_size = max_file_size

    def _iter_files(self, session_id: str):
        root = self._sessions_dir / session_id / "files"
        if not root.exists():
            return
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".txt", ".md", ".json", ".log", ".csv"}:
                continue
            try:
                if path.stat().st_size > self._max_file_size:
                    continue
            except OSError:
                continue
            yield path

    def search(
        self,
        *,
        session_id: str,
        query: str,
        top_k: int,
        agent_id: str | None = None,
        visible_events: list[dict] | None = None,
    ) -> list[dict]:
        del agent_id, visible_events
        rows: list[dict] = []
        for path in self._iter_files(session_id):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            score = _token_overlap_ratio(text[:2000], query)
            if score <= 0:
                continue
            snippet = text[:160].replace("\n", " ").strip()
            rel_path = str(path.relative_to(self._sessions_dir / session_id))
            rows.append(
                {
                    "ref_id": f"file:{session_id}:{rel_path}",
                    "semantic_sim": score,
                    "freshness": 0.5,
                    "dependency_graph": 0.2,
                    "payload": {"path": rel_path, "snippet": snippet},
                }
            )
        rows.sort(key=lambda x: x.get("semantic_sim", 0.0), reverse=True)
        return rows[:max(top_k, 1)]


class WebSearchProvider:
    """Web 检索：调用公开 HTTP 搜索入口，失败时返回空列表。"""

    def __init__(self, timeout_seconds: float = 5.0):
        self._timeout_seconds = timeout_seconds

    def search(
        self,
        *,
        session_id: str,
        query: str,
        top_k: int,
        agent_id: str | None = None,
        visible_events: list[dict] | None = None,
    ) -> list[dict]:
        del session_id, agent_id, visible_events
        q = urllib.parse.quote_plus(query)
        url = f"https://duckduckgo.com/?q={q}&format=json&no_redirect=1&no_html=1"
        req = urllib.request.Request(
            url=url,
            headers={"User-Agent": "GraphChat/0.1 (+https://example.local)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout_seconds) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            payload = json.loads(raw)
        except Exception:
            return []

        rows: list[dict] = []
        abstract = str(payload.get("AbstractText", "")).strip()
        abstract_url = str(payload.get("AbstractURL", "")).strip()
        heading = str(payload.get("Heading", "")).strip()
        if abstract:
            rows.append(
                {
                    "url": abstract_url,
                    "title": heading or "Abstract",
                    "snippet": abstract,
                    "semantic_sim": _token_overlap_ratio(f"{heading} {abstract}", query),
                    "freshness": 0.6,
                    "dependency_graph": 0.1,
                    "payload": {"title": heading, "url": abstract_url, "snippet": abstract},
                }
            )

        for topic in payload.get("RelatedTopics", []):
            if len(rows) >= max(top_k, 1):
                break
            if not isinstance(topic, dict):
                continue
            text = str(topic.get("Text", "")).strip()
            if not text:
                continue
            first_url = str(topic.get("FirstURL", "")).strip()
            rows.append(
                {
                    "url": first_url,
                    "title": text[:50],
                    "snippet": text,
                    "semantic_sim": _token_overlap_ratio(text, query),
                    "freshness": 0.55,
                    "dependency_graph": 0.1,
                    "payload": {"title": text[:50], "url": first_url, "snippet": text},
                }
            )
        return rows[:max(top_k, 1)]
