from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...workflow.engine import WorkflowEngine


@dataclass
class AppRuntime:
    world: Any
    store: Any
    query: Any
    proposer: Any
    interpreter: Any
    scheduler: Any
    router: Any
    controller: Any
    engine: WorkflowEngine
    ui_server: Any | None = None

