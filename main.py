"""Compatibility entrypoint. Preferred: `python -m agents_chat.app.cli`."""

from agents_chat.app.cli import build_runtime_config, main, parse_args
from agents_chat.app.runtime import run_session

__all__ = ["parse_args", "build_runtime_config", "run_session", "main"]


if __name__ == "__main__":
    main()

