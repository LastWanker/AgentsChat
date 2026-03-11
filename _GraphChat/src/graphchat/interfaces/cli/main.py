from __future__ import annotations

import argparse
import json
from pathlib import Path

from graphchat.application.runtime import GraphChatRuntime


def main() -> None:
    parser = argparse.ArgumentParser(description="GraphChat CLI demo")
    parser.add_argument("--session", default="demo_session")
    parser.add_argument("--text", default="大家好，我们先同步一下任务板。")
    parser.add_argument("--data-dir", default=str(Path("_GraphChat/data")))
    args = parser.parse_args()

    runtime = GraphChatRuntime(base_dir=args.data_dir)
    outputs = runtime.submit_user_text(session_id=args.session, text=args.text)
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

