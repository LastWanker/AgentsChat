from __future__ import annotations

import argparse
import urllib.error
import urllib.request
import webbrowser


def _ready(url: str, timeout: float) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return int(getattr(resp, "status", 0)) == 200
    except urllib.error.URLError:
        return False
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Open GraphChat internal console in browser")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--timeout", type=float, default=1.0)
    args = parser.parse_args()

    health_url = f"http://{args.host}:{args.port}/healthz"
    console_url = f"http://{args.host}:{args.port}/internal-console"
    if _ready(health_url, args.timeout):
        print(f"server_ready: {health_url}")
    else:
        print(f"server_not_ready: {health_url}")
        print("tip: start API server first: python _GraphChat/scripts/run_api_server.py")

    print(f"console: {console_url}")
    if not args.no_open:
        webbrowser.open(console_url, new=2)


if __name__ == "__main__":
    main()

