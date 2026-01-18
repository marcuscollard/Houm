from __future__ import annotations

import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        if not key:
            continue
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def get_maps_key() -> str:
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if key:
        return key
    env = load_env(ENV_PATH)
    return env.get("GOOGLE_MAPS_API_KEY", "")


class HoumHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/.env"):
            self.send_error(404)
            return
        if path == "/config":
            key = get_maps_key()
            body = json.dumps({"googleMapsApiKey": key}).encode("utf-8")
            self.send_response(200 if key else 500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def main() -> None:
    host = os.getenv("HOUM_HOST", "127.0.0.1")
    port = int(os.getenv("HOUM_PORT", "8000"))
    handler = partial(HoumHandler, directory=str(BASE_DIR))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Houm server running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
