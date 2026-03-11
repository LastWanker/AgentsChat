from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from agents.agent import Agent


@dataclass
class RuntimeConfig:
    agents: list[Agent]
    policy_path: str

    enable_llm: bool = False
    llm_client: Optional[object] = None
    llm_mode: str = "async"
    allow_empty_policy: bool = False

    data_dir: str = "data/sessions"
    session_id: Optional[str] = None
    resume_session_id: Optional[str] = None
    session_metadata: Optional[dict[str, Any]] = None

    ui_enabled: bool = False
    ui_auto_open: bool = False
    ui_host: str = "127.0.0.1"
    ui_port: int = 8000

    max_ticks: int = 50
    seed_events: Optional[list[dict]] = None
    scheduler_strategy: str = "recency"
    scheduler_strategy_config: Optional[dict[str, Any]] = None

    workflow_engine: str = "langgraph"
