from __future__ import annotations

import argparse
import json
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def find_browser() -> str:
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path.home() / r"AppData\Local\Microsoft\Edge\Application\msedge.exe",
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError("Could not find Microsoft Edge or Google Chrome on this machine.")


def launch_browser(repo_root: Path, connection_id: str, login_url: str, port: int, profile_relative_path: str | None = None) -> dict[str, Any]:
    profile_dir = repo_root / (profile_relative_path or f"private-data/integrations/{connection_id}/browser-profile")
    profile_dir.mkdir(parents=True, exist_ok=True)
    browser_exe = find_browser()
    args = [
        browser_exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--new-window",
        login_url,
    ]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {
        "status": "launched",
        "browser_exe": browser_exe,
        "profile_dir": str(profile_dir),
        "login_url": login_url,
        "debug_port": port,
    }


class BrowserBridgeHandler(BaseHTTPRequestHandler):
    server_version = "JobOpsBrowserBridge/1.0"

    @property
    def repo_root(self) -> Path:
        return Path(getattr(self.server, "repo_root"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/health":
            self._write_json(HTTPStatus.NOT_FOUND, {"detail": "Not Found"})
            return
        self._write_json(HTTPStatus.OK, {"status": "ok", "service": "browser_bridge"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/launch":
            self._write_json(HTTPStatus.NOT_FOUND, {"detail": "Not Found"})
            return
        try:
            payload = self._read_json()
            connection_id = str(payload.get("connection_id") or "").strip()
            login_url = str(payload.get("login_url") or "").strip()
            port = int(payload.get("port"))
            profile_relative_path = payload.get("profile_relative_path")
            if not connection_id:
                raise ValueError("connection_id is required")
            if not login_url:
                raise ValueError("login_url is required")
            result = launch_browser(self.repo_root, connection_id, login_url, port, str(profile_relative_path) if profile_relative_path else None)
            self._write_json(HTTPStatus.OK, result)
        except FileNotFoundError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"status": "error", "detail": str(exc)})
        except Exception as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"status": "error", "detail": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch a host-side browser bridge for JobOps guided sign-in.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), BrowserBridgeHandler)
    server.repo_root = Path(args.repo_root).resolve()
    print(f"Browser bridge listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
