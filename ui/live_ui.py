#!/usr/bin/env python3
"""Lightweight live UI server for AgentsChat events."""
from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from collections import deque
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Deque, Dict, List, Mapping
from urllib.parse import parse_qs, urlparse


def _list_sessions(base_dir: Path) -> List[Dict[str, str]]:
    if not base_dir.exists():
        return []
    sessions: List[Dict[str, str]] = []
    for entry in base_dir.iterdir():
        if entry.is_dir():
            sessions.append(
                {
                    "session_id": entry.name,
                    "mtime": str(entry.stat().st_mtime),
                }
            )
    sessions.sort(key=lambda item: float(item["mtime"]), reverse=True)
    return sessions


def _read_events(events_path: Path, limit: int) -> List[Dict]:
    events: Deque[Dict] = deque(maxlen=limit)
    if not events_path.exists():
        return []
    with events_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return list(events)


def _load_agent_names(session_dir: Path) -> Mapping[str, str]:
    meta_path = session_dir / "meta.json"
    if not meta_path.exists():
        return {}
    try:
        with meta_path.open("r", encoding="utf-8") as handle:
            meta = json.load(handle)
    except json.JSONDecodeError:
        return {}
    agents = meta.get("agents") or []
    names: Dict[str, str] = {}
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        agent_id = agent.get("id")
        name = agent.get("name")
        if agent_id and name:
            names[str(agent_id)] = str(name)
    return names


class LiveUIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, data_dir: Path, default_session: str | None, **kwargs):
        self.data_dir = data_dir
        self.default_session = default_session
        super().__init__(*args, directory=directory, **kwargs)

    def _send_json(self, payload: Dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802 - keep for handler signature
        parsed = urlparse(self.path)
        if parsed.path == "/api/sessions":
            sessions = _list_sessions(self.data_dir)
            latest = sessions[0]["session_id"] if sessions else None
            self._send_json({"sessions": sessions, "latest": latest})
            return

        if parsed.path == "/api/events":
            query = parse_qs(parsed.query)
            session_id = query.get("session", [self.default_session])[-1]
            limit = int(query.get("limit", [200])[-1])
            events_path = None
            if session_id:
                events_path = self.data_dir / session_id / "events.jsonl"
            events = _read_events(events_path, limit) if events_path else []
            if session_id:
                agent_names = _load_agent_names(self.data_dir / session_id)
                if agent_names:
                    for event in events:
                        if isinstance(event, dict):
                            sender = event.get("sender")
                            name = agent_names.get(str(sender))
                            if name:
                                event["sender_name"] = name
            self._send_json({"session_id": session_id, "events": events})
            return

        if parsed.path in {"/", "/index.html"}:
            self.path = "/live_ui.html"
        return super().do_GET()

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - keep handler signature
        parsed = urlparse(self.path)
        if parsed.path == "/api/events":
            return
        super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description="AgentsChat live UI server")
    parser.add_argument("--data-dir", default="data/sessions", help="events data dir")
    parser.add_argument("--session-id", default=None, help="session id to load")
    parser.add_argument("--host", default="0.0.0.0", help="host to bind")
    parser.add_argument("--port", type=int, default=8000, help="port to serve")
    parser.add_argument("--auto-open", action="store_true", help="auto open UI in browser")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    sessions = _list_sessions(data_dir)
    default_session = args.session_id or (sessions[0]["session_id"] if sessions else None)

    directory = Path(__file__).resolve().parent
    handler = partial(
        LiveUIHandler,
        directory=str(directory),
        data_dir=data_dir,
        default_session=default_session,
    )

    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(
        "[ui/live_ui.py] Serving live UI at http://%s:%d (session=%s)"
        % (args.host, args.port, default_session or "none")
    )
    if args.auto_open:
        open_host = args.host if args.host != "0.0.0.0" else "127.0.0.1"
        webbrowser.open(f"http://{open_host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[ui/live_ui.py] Stopped.")
    finally:
        server.server_close()


def start_live_ui_server(
        *,
        data_dir: Path,
        session_id: str | None,
        host: str,
        port: int,
        auto_open: bool,
) -> ThreadingHTTPServer | None:
    directory = Path(__file__).resolve().parent
    handler = partial(
        LiveUIHandler,
        directory=str(directory),
        data_dir=data_dir,
        default_session=session_id,
    )
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        print(f"[ui/live_ui.py] ⚠️ 无法启动 UI server: {exc}")
        return None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(
        "[ui/live_ui.py] 🖥️ Live UI 已后台启动: http://%s:%d (session=%s)"
        % (host, port, session_id or "none")
    )
    if auto_open:
        open_host = host if host != "0.0.0.0" else "127.0.0.1"
        webbrowser.open(f"http://{open_host}:{port}")
    return server


if __name__ == "__main__":
    main()
