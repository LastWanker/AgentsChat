from __future__ import annotations

from dataclasses import dataclass, replace

from graphchat.domain.models.action_contract import ActionSpec


BOARD_ACTIONS = {
    "maintain_board",
    "assign_task",
    "board_item_upserted",
    "board_item_deleted",
    "board_item_archived",
    "board_item_priority_set",
    "board_item_due_set",
    "board_gc_performed",
}
GOVERNANCE_ACTIONS = {"vote_decision", "dissolve_group"}


@dataclass(frozen=True)
class SkillGuardProfile:
    """Per-skill execution profile.

    This controls both skill-stage execution and attached guard chain.
    """

    skill_id: str
    run_retrieval: bool = False
    run_board_subgraph: bool = False
    run_governance_subgraph: bool = False
    enable_citation_guard: bool = False
    enable_policy_guard: bool = True
    enable_schema_guard: bool = True
    enable_registry_guard: bool = True
    enable_idempotency_guard: bool = True
    emit_event: bool = True


def default_profile_for_action(action_id: str, spec: ActionSpec | None = None) -> SkillGuardProfile:
    action = str(action_id).strip()
    if action == "rag":
        return SkillGuardProfile(
            skill_id="rag",
            run_retrieval=True,
            enable_citation_guard=True,
            enable_policy_guard=False,
            enable_schema_guard=False,
            enable_registry_guard=False,
            enable_idempotency_guard=False,
            emit_event=False,
        )
    if action == "listen_only":
        return SkillGuardProfile(
            skill_id=action,
            enable_policy_guard=False,
            enable_schema_guard=False,
            enable_registry_guard=False,
            enable_idempotency_guard=False,
            emit_event=False,
        )

    citation_policy = str(spec.citation_policy) if spec is not None else "none"
    return SkillGuardProfile(
        skill_id=action,
        run_retrieval=bool(spec.needs_retrieval) if spec is not None else False,
        run_board_subgraph=action in BOARD_ACTIONS,
        run_governance_subgraph=action in GOVERNANCE_ACTIONS,
        enable_citation_guard=citation_policy != "none",
        enable_policy_guard=True,
        enable_schema_guard=True,
        enable_registry_guard=True,
        enable_idempotency_guard=True,
        emit_event=True,
    )


def build_default_skill_profiles(
    action_registry: dict[str, ActionSpec],
    overrides: dict[str, SkillGuardProfile] | None = None,
) -> dict[str, SkillGuardProfile]:
    profiles: dict[str, SkillGuardProfile] = {}
    for action_id, spec in action_registry.items():
        profiles[action_id] = default_profile_for_action(action_id, spec)
    profiles["rag"] = default_profile_for_action("rag", None)
    profiles["listen_only"] = default_profile_for_action("listen_only", None)
    if overrides:
        for action_id, profile in overrides.items():
            profiles[action_id] = profile
    return profiles


def apply_profile_overrides(
    profiles: dict[str, SkillGuardProfile],
    overrides: dict[str, dict] | None = None,
) -> dict[str, SkillGuardProfile]:
    if not overrides:
        return profiles
    out = dict(profiles)
    for action_id, patch in overrides.items():
        if not isinstance(patch, dict):
            continue
        base = out.get(action_id) or default_profile_for_action(action_id, None)
        fields = {key: value for key, value in patch.items() if hasattr(base, key)}
        out[action_id] = replace(base, **fields)
    return out
