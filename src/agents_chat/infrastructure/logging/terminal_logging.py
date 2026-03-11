from __future__ import annotations

import atexit
import sys
from pathlib import Path
from typing import TextIO

from .tee_stream import TeeStream


def enable_terminal_logging(session_dir: Path) -> None:
    log_path = session_dir / "terminal.log"
    log_file = log_path.open("a", encoding="utf-8")

    def _wrap(stream: TextIO) -> TextIO:
        if getattr(stream, "_tee_log_path", None) == log_path:
            return stream
        return TeeStream(stream, log_file, log_path)

    sys.stdout = _wrap(sys.stdout)
    sys.stderr = _wrap(sys.stderr)
    def _safe_close() -> None:
        try:
            log_file.flush()
        except Exception:
            pass
        try:
            log_file.close()
        except Exception:
            pass

    atexit.register(_safe_close)
    print(f"[infrastructure/logging] terminal log -> {log_path}")
