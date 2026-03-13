from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from src.graphchat import GraphChatRuntime  # noqa: E402


def main() -> None:
    runtime = GraphChatRuntime(base_dir=ROOT / "data")
    outputs = runtime.submit_user_text(
        session_id="demo_session",
        text="请大家围绕这个议题投票，并更新任务板。",
    )
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
