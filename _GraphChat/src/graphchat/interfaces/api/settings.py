from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class APISettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    data_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "data")
    log_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "logs")
    api_token: str = ""
    checkpointer_backend: Literal["auto", "memory", "sqlite"] = "auto"

    @classmethod
    def from_env(cls) -> "APISettings":
        host = os.getenv("GRAPHCHAT_HOST", "127.0.0.1").strip() or "127.0.0.1"
        port = int(os.getenv("GRAPHCHAT_PORT", "8000"))
        log_level = os.getenv("GRAPHCHAT_LOG_LEVEL", "info").strip() or "info"
        data_dir = Path(os.getenv("GRAPHCHAT_DATA_DIR", str(PROJECT_ROOT / "data"))).resolve()
        log_dir = Path(os.getenv("GRAPHCHAT_LOG_DIR", str(PROJECT_ROOT / "logs"))).resolve()
        api_token = os.getenv("GRAPHCHAT_API_TOKEN", "").strip()
        backend = os.getenv("GRAPHCHAT_CHECKPOINTER_BACKEND", "auto").strip().lower()
        if backend not in {"auto", "memory", "sqlite"}:
            backend = "auto"
        return cls(
            host=host,
            port=port,
            log_level=log_level,
            data_dir=data_dir,
            log_dir=log_dir,
            api_token=api_token,
            checkpointer_backend=backend,
        )
