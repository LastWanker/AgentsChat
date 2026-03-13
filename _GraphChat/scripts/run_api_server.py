from __future__ import annotations

import argparse
from pathlib import Path
import sys


def _bootstrap_src() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    _bootstrap_src()
    from src.graphchat.interfaces.api.server import configure_logging, create_app
    from src.graphchat.interfaces.api.settings import APISettings

    parser = argparse.ArgumentParser(description="Run GraphChat internal API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--log-level", default="info")
    parser.add_argument("--data-dir", default=str(root / "data"))
    parser.add_argument("--log-dir", default=str(root / "logs"))
    parser.add_argument("--api-token", default="")
    parser.add_argument("--checkpointer-backend", default="auto", choices=["auto", "memory", "sqlite"])
    args = parser.parse_args()

    settings = APISettings(
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        data_dir=Path(args.data_dir).resolve(),
        log_dir=Path(args.log_dir).resolve(),
        api_token=args.api_token,
        checkpointer_backend=args.checkpointer_backend,
    )
    configure_logging(settings)
    app = create_app(settings=settings)

    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("uvicorn is required to run GraphChat API server") from exc
    uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level)


if __name__ == "__main__":
    main()
