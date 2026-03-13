from __future__ import annotations

import argparse
import json
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
    _bootstrap_src()
    from src.graphchat import GraphChatRuntime

    parser = argparse.ArgumentParser(description="M6 minimal app demo")
    parser.add_argument("--session", default="m6_demo")
    parser.add_argument("--data-dir", default=str(Path("_GraphChat/data")))
    args = parser.parse_args()

    with GraphChatRuntime(base_dir=args.data_dir) as runtime:
        session_id = args.session
        print("[M6] bootstrap groups + agents")
        runtime.submit_world_command(
            session_id=session_id,
            command={"type": "create_agent", "payload": {"agent_id": "agent_4", "enabled": True}},
            created_by="boss",
        )
        runtime.submit_world_commands(
            session_id=session_id,
            created_by="boss",
            commands=[
                {"type": "upsert_group", "payload": {"group_id": "team_1", "members": ["agent_1", "agent_2"]}},
                {"type": "upsert_group", "payload": {"group_id": "team_2", "members": ["agent_3", "agent_4"]}},
                {
                    "type": "set_agent_retrieval",
                    "payload": {"agent_id": "agent_1", "channels": ["web_search", "world_history"]},
                },
                {"type": "set_agent_retrieval", "payload": {"agent_id": "agent_2", "channels": ["file_search"]}},
            ],
        )

        print("[M6] command: team_1 sync")
        out_team_1 = runtime.submit_user_text(session_id=session_id, world_scope="group:team_1", text="team_1 同步进展")
        print(json.dumps(out_team_1, ensure_ascii=False, indent=2))

        print("[M6] command: team_1 search")
        out_search = runtime.submit_user_text(session_id=session_id, world_scope="group:team_1", text="请查一下资料并汇总")
        print(json.dumps(out_search, ensure_ascii=False, indent=2))

        print("[M6] world inject: team_2 discuss")
        out_inject = runtime.submit_world_command(
            session_id=session_id,
            created_by="boss",
            command={
                "type": "inject_task",
                "scope": "group:team_2",
                "payload": {"text": "请在 team_2 分组讨论并给结论", "urgency": "normal"},
            },
        )
        print(json.dumps(out_inject, ensure_ascii=False, indent=2))

        print("[M6] direct chat with each agent")
        for agent_id in runtime.agents:
            reply = runtime.direct_chat_with_agent(
                session_id=session_id,
                agent_id=agent_id,
                text="请一句话汇报你当前状态",
            )
            if reply is not None:
                print(json.dumps(reply, ensure_ascii=False, indent=2))

        print("[M6] observability snapshot")
        print(json.dumps(runtime.get_observability_snapshot(session_id=session_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
