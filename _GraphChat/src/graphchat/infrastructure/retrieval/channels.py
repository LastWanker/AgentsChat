from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from graphchat.infrastructure.retrieval.tag_index import TagInvertedIndex
from graphchat.infrastructure.retrieval.vector_index import VectorIndex


def _token_overlap_ratio(text: str, query: str) -> float:
    q = set(str(query).lower().split())
    t = set(str(text).lower().split())
    if not q or not t:
        return 0.0
    return len(q & t) / max(len(q | t), 1)


@dataclass(frozen=True)
class RetrievalContext:
    session_id: str
    agent_id: str
    query: str
    visible_events: list[dict]


class SearchProvider(Protocol):
    def search(
        self,
        *,
        session_id: str,
        query: str,
        top_k: int,
        agent_id: str | None = None,
        visible_events: list[dict] | None = None,
    ) -> list[dict]:
        ...


class NoopSearchProvider:
    """待拓展：替换为真实 Web/File 检索客户端。"""

    def search(
        self,
        *,
        session_id: str,
        query: str,
        top_k: int,
        agent_id: str | None = None,
        visible_events: list[dict] | None = None,
    ) -> list[dict]:
        return []


class RetrievalChannel(Protocol):
    channel_id: str

    def retrieve(self, ctx: RetrievalContext, top_k: int = 5) -> list[dict]:
        ...


class WorldHistoryChannel:
    channel_id = "world_history"

    def __init__(self, tag_index: TagInvertedIndex, vector_index: VectorIndex):
        self._tag_index = tag_index
        self._vector_index = vector_index

    def retrieve(self, ctx: RetrievalContext, top_k: int = 5) -> list[dict]:
        results: list[dict] = []
        recent = list(ctx.visible_events)[-max(top_k * 2, 6) :]
        total = max(len(recent), 1)
        for idx, event in enumerate(reversed(recent)):
            event_id = event.get("event_id")
            if not event_id:
                continue
            payload = event.get("payload", {})
            text = str(payload.get("text", ""))
            semantic = _token_overlap_ratio(text, ctx.query)
            freshness = 1.0 - (idx / total)
            dependency = 0.6 if event.get("focus_reference") else 0.2
            results.append(
                {
                    "event_id": event_id,
                    "source": self.channel_id,
                    "channel": self.channel_id,
                    "semantic_sim": semantic,
                    "freshness": freshness,
                    "dependency_graph": dependency,
                    "source_weight": 0.9,
                    "payload": {"text": text},
                }
            )

        for item in self._tag_index.search(ctx.query, top_k=top_k):
            if not item.get("event_id"):
                continue
            results.append(
                {
                    "event_id": item["event_id"],
                    "source": "tag_index",
                    "channel": self.channel_id,
                    "semantic_sim": float(item.get("score", 0.0)),
                    "freshness": 0.4,
                    "dependency_graph": 0.2,
                    "source_weight": 0.55,
                    "payload": {},
                }
            )

        for item in self._vector_index.search(ctx.query, top_k=top_k):
            if not item.get("event_id"):
                continue
            results.append(
                {
                    "event_id": item["event_id"],
                    "source": "vector_index",
                    "channel": self.channel_id,
                    "semantic_sim": float(item.get("score", 0.0)),
                    "freshness": 0.5,
                    "dependency_graph": 0.25,
                    "source_weight": 0.65,
                    "payload": {},
                }
            )
        return results


class AskPeerChannel:
    channel_id = "ask_peer"

    def __init__(self, provider: SearchProvider | None = None):
        self._provider = provider

    def retrieve(self, ctx: RetrievalContext, top_k: int = 5) -> list[dict]:
        if self._provider is not None:
            rows = self._provider.search(
                session_id=ctx.session_id,
                query=ctx.query,
                top_k=top_k,
                agent_id=ctx.agent_id,
                visible_events=ctx.visible_events,
            )
            results: list[dict] = []
            for row in rows:
                event_id = str(row.get("event_id") or row.get("ref_id") or "")
                if not event_id:
                    continue
                results.append(
                    {
                        "event_id": event_id,
                        "source": self.channel_id,
                        "channel": self.channel_id,
                        "semantic_sim": float(row.get("semantic_sim", 0.5)),
                        "freshness": float(row.get("freshness", 0.6)),
                        "dependency_graph": float(row.get("dependency_graph", 0.35)),
                        "source_weight": 0.7,
                        "payload": row.get("payload", {}),
                    }
                )
            return results

        results: list[dict] = []
        peer_events = [
            event
            for event in reversed(ctx.visible_events)
            if event.get("actor_id") not in {None, "", ctx.agent_id}
        ]
        for idx, event in enumerate(peer_events[:top_k]):
            event_id = event.get("event_id")
            if not event_id:
                continue
            text = str(event.get("payload", {}).get("text", ""))
            results.append(
                {
                    "event_id": event_id,
                    "source": self.channel_id,
                    "channel": self.channel_id,
                    "semantic_sim": _token_overlap_ratio(text, ctx.query),
                    "freshness": 1.0 - idx / max(top_k, 1),
                    "dependency_graph": 0.35,
                    "source_weight": 0.7,
                    "payload": {"text": text},
                }
            )
        return results


class FileSearchChannel:
    channel_id = "file_search"

    def __init__(self, provider: SearchProvider | None = None):
        self._provider = provider or NoopSearchProvider()

    def retrieve(self, ctx: RetrievalContext, top_k: int = 5) -> list[dict]:
        rows = self._provider.search(
            session_id=ctx.session_id,
            query=ctx.query,
            top_k=top_k,
            agent_id=ctx.agent_id,
            visible_events=ctx.visible_events,
        )
        results: list[dict] = []
        for row in rows:
            ref_id = str(row.get("event_id") or row.get("ref_id") or "")
            if not ref_id:
                continue
            results.append(
                {
                    "event_id": ref_id,
                    "source": self.channel_id,
                    "channel": self.channel_id,
                    "semantic_sim": float(row.get("semantic_sim", 0.5)),
                    "freshness": float(row.get("freshness", 0.5)),
                    "dependency_graph": float(row.get("dependency_graph", 0.2)),
                    "source_weight": 0.8,
                    "payload": row.get("payload", {}),
                }
            )
        return results


class WebSearchChannel:
    channel_id = "web_search"

    def __init__(self, provider: SearchProvider | None = None):
        self._provider = provider or NoopSearchProvider()

    def retrieve(self, ctx: RetrievalContext, top_k: int = 5) -> list[dict]:
        rows = self._provider.search(
            session_id=ctx.session_id,
            query=ctx.query,
            top_k=top_k,
            agent_id=ctx.agent_id,
            visible_events=ctx.visible_events,
        )
        results: list[dict] = []
        for idx, row in enumerate(rows[:top_k]):
            title = str(row.get("title") or row.get("snippet") or "")
            ref_id = str(row.get("event_id") or row.get("url") or f"web:{ctx.session_id}:{idx}")
            results.append(
                {
                    "event_id": ref_id,
                    "source": self.channel_id,
                    "channel": self.channel_id,
                    "semantic_sim": float(row.get("semantic_sim", _token_overlap_ratio(title, ctx.query))),
                    "freshness": float(row.get("freshness", 0.6)),
                    "dependency_graph": float(row.get("dependency_graph", 0.1)),
                    "source_weight": 0.6,
                    "payload": row.get("payload", {"title": title, "url": row.get("url", "")}),
                }
            )
        return results


def build_default_channels(
    *,
    tag_index: TagInvertedIndex,
    vector_index: VectorIndex,
    peer_provider: SearchProvider | None = None,
    web_provider: SearchProvider | None = None,
    file_provider: SearchProvider | None = None,
) -> dict[str, RetrievalChannel]:
    return {
        "world_history": WorldHistoryChannel(tag_index=tag_index, vector_index=vector_index),
        "ask_peer": AskPeerChannel(provider=peer_provider),
        "file_search": FileSearchChannel(provider=file_provider),
        "web_search": WebSearchChannel(provider=web_provider),
    }
