from __future__ import annotations

from events.intention_schemas import IntentionDraft
from events.tagging import generate_tags
from events.types import Intention


def choose_turn_agent(controller, scheduler, tick_index: int):
    return scheduler.choose_agent(controller.agents, loop_tick=tick_index)


def build_fallback_intention(agent, draft: IntentionDraft) -> Intention:
    domain = getattr(agent, "expertise", []) or []
    fixed = [
        str(getattr(agent, "name", agent.id)),
        str(domain[0] if domain else getattr(agent, "role", "general")),
    ]
    text = draft.draft_text or draft.message_plan
    tags = generate_tags(text=text, fixed_prefix=fixed, max_tags=6)
    return Intention(
        intention_id=draft.intention_id,
        agent_id=agent.id,
        kind="speak",
        payload={"text": f"{agent.name} interest too low for this turn, skip speaking."},
        references=[],
        tags=tags,
        confidence=draft.confidence,
        motivation=draft.motivation,
        urgency=draft.urgency,
    )

