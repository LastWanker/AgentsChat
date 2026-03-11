from __future__ import annotations

from collections import defaultdict


class TagInvertedIndex:
    def __init__(self):
        self._index: dict[str, set[str]] = defaultdict(set)

    def add(self, text: str, event_id: str) -> None:
        for token in text.split():
            self._index[token.lower()].add(event_id)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        hit_count: dict[str, int] = defaultdict(int)
        for token in query.split():
            for event_id in self._index.get(token.lower(), set()):
                hit_count[event_id] += 1
        ranked = sorted(hit_count.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [{"event_id": event_id, "score": 0.4 + score * 0.1, "source": "tag_index"} for event_id, score in ranked]

