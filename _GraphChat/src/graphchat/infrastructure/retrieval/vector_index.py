from __future__ import annotations


class VectorIndex:
    def __init__(self):
        self._rows: list[tuple[str, str]] = []

    def add(self, text: str, event_id: str) -> None:
        self._rows.append((text.lower(), event_id))

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        q_set = set(query.lower().split())
        scored: list[tuple[str, float]] = []
        for text, event_id in self._rows:
            t_set = set(text.split())
            if not q_set or not t_set:
                continue
            score = len(q_set & t_set) / max(len(q_set | t_set), 1)
            if score > 0:
                scored.append((event_id, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [{"event_id": event_id, "score": float(score), "source": "vector_index"} for event_id, score in scored[:top_k]]

