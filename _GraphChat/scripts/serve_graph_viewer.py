from __future__ import annotations

import argparse
import http.server
import socketserver
import subprocess
import sys
import webbrowser
from pathlib import Path


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def _bind_server(
    host: str,
    start_port: int,
    max_tries: int,
    handler_cls: type[http.server.SimpleHTTPRequestHandler],
) -> tuple[ReusableTCPServer, int]:
    last_error: OSError | None = None
    for offset in range(max_tries):
        port = start_port + offset
        try:
            server = ReusableTCPServer((host, port), handler_cls)
            return server, port
        except OSError as e:
            last_error = e
            continue
    raise SystemExit(
        f"failed to bind server on {host}:{start_port}..{start_port + max_tries - 1}; "
        f"last_error={last_error}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export and serve graph viewer")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="Project root of _GraphChat")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port-tries", type=int, default=30, help="How many consecutive ports to try")
    parser.add_argument("--no-open", action="store_true", help="Do not auto-open browser")
    parser.add_argument("--no-export", action="store_true", help="Skip export and serve existing files")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not args.no_export:
        subprocess.run(
            [
                sys.executable,
                str(root / "scripts" / "export_graph_viewer.py"),
                "--root",
                str(root),
                "--no-open",
            ],
            check=True,
        )

    web_dir = root / "docs" / "graphs"
    if not web_dir.exists():
        raise SystemExit(f"missing dir: {web_dir}")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *h_args, **h_kwargs):
            super().__init__(*h_args, directory=str(web_dir), **h_kwargs)

    httpd, port = _bind_server(args.host, args.port, args.port_tries, Handler)
    with httpd:
        host = str(httpd.server_address[0])
        url = f"http://{host}:{port}/graph_viewer.html"
        if port != args.port:
            print(f"port_fallback: requested={args.port}, using={port}")
        print(f"viewer: {url}")
        if not args.no_open:
            try:
                webbrowser.open(url, new=2)
                print("browser_opened: viewer opened")
            except Exception as e:  # pragma: no cover
                print(f"browser_open_failed: {e}")
        print("press Ctrl+C to stop")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
