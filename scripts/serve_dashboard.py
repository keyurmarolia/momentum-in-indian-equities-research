"""Loopback-only server for the built static research dashboard."""

import argparse
import json
import urllib.request
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    folder = ROOT / "dashboard/dist"
    url = f"http://127.0.0.1:{args.port}/"
    if not (folder / "index.html").exists():
        raise SystemExit("Dashboard not installed. Run: python scripts/setup_research.py")
    if not (folder / "data/manifest.json").exists() or not (folder / "plotly.min.js").exists():
        raise SystemExit("Dashboard data/assets not installed. Run: python scripts/setup_research.py")
    handler = partial(SimpleHTTPRequestHandler, directory=str(folder))
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    except OSError:
        try:
            with urllib.request.urlopen(url + "dashboard-status.json", timeout=2) as response:
                identity = json.load(response)
            if identity.get("application") != "momentum-research-explorer":
                raise ValueError("Different application")
        except Exception:
            raise SystemExit(f"Port {args.port} is occupied by another application.") from None
        if not args.no_open:
            webbrowser.open(url)
        print("Research dashboard is already running: " + url)
        return
    print("Research dashboard: " + url, flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
