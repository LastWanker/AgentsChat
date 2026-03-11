from __future__ import annotations

from collections import defaultdict


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def value_score(candidate: dict) -> float:
    # 规则优先：特征都由系统计算，避免 LLM 直接“拍分”。
    semantic_sim = _clamp(candidate.get("semantic_sim", 0.0))
    source_weight = _clamp(candidate.get("source_weight", 0.0))
    freshness = _clamp(candidate.get("freshness", 0.0))
    dependency_graph = _clamp(candidate.get("dependency_graph", 0.0))
    consensus = _clamp(candidate.get("consensus", 0.0))
    return (
        0.45 * semantic_sim
        + 0.20 * source_weight
        + 0.15 * freshness
        + 0.10 * dependency_graph
        + 0.10 * consensus
    )


def merge_and_rank_candidates(raw_candidates: list[dict], total_channels: int, top_k: int = 8) -> list[dict]:
    if not raw_candidates:
        return []

    per_id: dict[str, dict] = {}
    per_id_channels: dict[str, set[str]] = defaultdict(set)

    for item in raw_candidates:
        event_id = str(item.get("event_id", "")).strip()
        if not event_id:
            continue
        channel = str(item.get("channel", item.get("source", "unknown")))
        per_id_channels[event_id].add(channel)

        current = per_id.get(event_id, {"event_id": event_id, "payload": {}, "sources": []})
        current["semantic_sim"] = max(float(current.get("semantic_sim", 0.0)), float(item.get("semantic_sim", 0.0)))
        current["source_weight"] = max(float(current.get("source_weight", 0.0)), float(item.get("source_weight", 0.0)))
        current["freshness"] = max(float(current.get("freshness", 0.0)), float(item.get("freshness", 0.0)))
        current["dependency_graph"] = max(
            float(current.get("dependency_graph", 0.0)),
            float(item.get("dependency_graph", 0.0)),
        )
        src = str(item.get("source", channel))
        if src and src not in current["sources"]:
            current["sources"].append(src)
        payload = item.get("payload", {})
        if isinstance(payload, dict):
            current["payload"] = {**current.get("payload", {}), **payload}
        per_id[event_id] = current

    denom = max(total_channels, 1)
    ranked: list[dict] = []
    for event_id, item in per_id.items():
        channels = sorted(per_id_channels[event_id])
        item["channels"] = channels
        item["consensus"] = _clamp(len(channels) / denom)
        item["score"] = round(value_score(item), 6)
        ranked.append(item)

    ranked.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return ranked[:top_k]

