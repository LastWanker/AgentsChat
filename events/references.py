from __future__ import annotations

from copy import deepcopy

from .types import Reference


def ref_event_id(ref: Reference | str) -> str:
    """Return the referenced event_id from a Reference.

    Accepts legacy plain string references for compatibility but encourages
    structured references that include explicit weights.
    """
    if isinstance(ref, str):
        return ref
    event_id = ref.get("event_id")
    if not event_id:
        raise KeyError("Reference missing required 'event_id'")
    return event_id


def default_ref_weight() -> dict[str, float]:
    """Return a neutral reference weight."""
    return {"stance": 0.0, "inspiration": 0.0, "dependency": 0.0}


def normalize_reference(ref: Reference | str) -> Reference:
    """Ensure reference carries an event_id and complete weight fields."""

    if isinstance(ref, str):
        return {"event_id": ref, "weight": default_ref_weight()}

    normalized: Reference = {"event_id": ref_event_id(ref)}
    weight = default_ref_weight()
    weight.update(deepcopy(ref.get("weight", {})))
    normalized["weight"] = weight
    return normalized


def normalize_references(refs: list[Reference | str]) -> list[Reference]:
    """Normalize a list of references, filling weights neutrally."""

    return [normalize_reference(r) for r in refs]