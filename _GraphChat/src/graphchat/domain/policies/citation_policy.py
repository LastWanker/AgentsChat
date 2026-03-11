from __future__ import annotations


def check_citation_policy(
    citation_policy: str,
    focus_reference: str | None,
    candidates: list[dict],
) -> tuple[bool, str]:
    candidate_ids = {c.get("event_id") for c in candidates if c.get("event_id")}

    if citation_policy == "none":
        return True, ""
    if citation_policy == "optional":
        if focus_reference and focus_reference not in candidate_ids:
            return False, "focus_reference 不在候选集"
        return True, ""
    if citation_policy == "required_focus":
        if not focus_reference:
            return False, "required_focus 缺少 focus_reference"
        if focus_reference not in candidate_ids:
            return False, "required_focus 的 focus_reference 不在候选集"
        return True, ""
    return False, f"未知 citation_policy: {citation_policy}"

