from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from langgraph.checkpoint.memory import InMemorySaver

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except Exception:  # pragma: no cover
    SqliteSaver = None  # type: ignore[assignment]


CheckpointBackend = Literal["auto", "memory", "sqlite"]


@dataclass
class CheckpointerHandle:
    saver: object
    close: Callable[[], None]
    backend: str
    location: str


def _build_memory_checkpointer() -> CheckpointerHandle:
    return CheckpointerHandle(
        saver=InMemorySaver(),
        close=lambda: None,
        backend="memory",
        location="in-memory",
    )


def _build_sqlite_checkpointer(sqlite_path: Path) -> CheckpointerHandle:
    if SqliteSaver is None:
        raise RuntimeError("langgraph-checkpoint-sqlite 未安装，无法使用 sqlite checkpointer")
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(sqlite_path), check_same_thread=False)
    saver = SqliteSaver(conn)
    return CheckpointerHandle(
        saver=saver,
        close=conn.close,
        backend="sqlite",
        location=str(sqlite_path),
    )


def build_checkpointer(
    backend: CheckpointBackend = "auto",
    sqlite_path: Path | None = None,
) -> CheckpointerHandle:
    if backend == "memory":
        return _build_memory_checkpointer()

    if backend == "sqlite":
        if sqlite_path is None:
            raise ValueError("backend=sqlite 时必须提供 sqlite_path")
        return _build_sqlite_checkpointer(sqlite_path)

    # backend=auto
    if sqlite_path is not None and SqliteSaver is not None:
        return _build_sqlite_checkpointer(sqlite_path)
    return _build_memory_checkpointer()


def build_runtime_checkpointers(
    base_dir: Path,
    backend: CheckpointBackend = "auto",
) -> tuple[CheckpointerHandle, CheckpointerHandle]:
    checkpoint_dir = base_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    world_handle = build_checkpointer(
        backend=backend,
        sqlite_path=checkpoint_dir / "world_checkpoints.sqlite",
    )
    agent_handle = build_checkpointer(
        backend=backend,
        sqlite_path=checkpoint_dir / "agent_checkpoints.sqlite",
    )
    return world_handle, agent_handle
