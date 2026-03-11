from __future__ import annotations

from pathlib import Path
from typing import TextIO


class TeeStream:
    def __init__(self, stream: TextIO, log_file: TextIO, log_path: Path):
        self._stream = stream
        self._log_file = log_file
        self._tee_log_path = log_path

    def write(self, message: str) -> int:
        self._log_file.write(message)
        return self._stream.write(message)

    def flush(self) -> None:
        try:
            self._log_file.flush()
        except Exception:
            pass
        self._stream.flush()

    def isatty(self) -> bool:
        return getattr(self._stream, "isatty", lambda: False)()

    @property
    def encoding(self) -> str | None:
        return getattr(self._stream, "encoding", None)
