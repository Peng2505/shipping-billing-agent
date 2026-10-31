"""Minimal token-gated file server for Cloudflare Tunnel OCR probes.

Serves ONLY pre-registered synthetic files under /t/<token>/<name>.
Does not expose the filesystem. Logs every request for OCR GET evidence.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlsplit


@dataclass
class ServedFile:
    name: str
    path: Path
    content_type: str
    max_bytes: int
    marker: str


@dataclass
class AccessEvent:
    ts: str
    method: str
    path: str
    client: str
    user_agent: str
    status: int
    bytes_sent: int
    elapsed_ms: int
    matched_token: str | None = None
    matched_file: str | None = None


@dataclass
class ServerState:
    files_by_token: dict[str, ServedFile]
    max_requests_total: int = 40
    request_count: int = 0
    events: list[AccessEvent] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


def make_handler(state: ServerState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args) -> None:  # silence default stderr spam
            return

        def _client(self) -> str:
            return self.client_address[0] if self.client_address else "?"

        def _record(self, method: str, status: int, sent: int, started: float,
                    token: str | None = None, name: str | None = None) -> None:
            ev = AccessEvent(
                ts=datetime.now(timezone.utc).isoformat(),
                method=method,
                path=self.path,
                client=self._client(),
                user_agent=self.headers.get("User-Agent", ""),
                status=status,
                bytes_sent=sent,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                matched_token=token,
                matched_file=name,
            )
            with state.lock:
                state.events.append(ev)

        def do_GET(self) -> None:  # noqa: N802
            started = time.monotonic()
            with state.lock:
                state.request_count += 1
                if state.request_count > state.max_requests_total:
                    self.send_error(429, "request budget exceeded")
                    self._record("GET", 429, 0, started)
                    return

            parts = urlsplit(self.path)
            path = unquote(parts.path)
            segs = [s for s in path.split("/") if s]
            # Expected: /t/<token>/<filename>
            if len(segs) != 3 or segs[0] != "t":
                self.send_error(404, "not found")
                self._record("GET", 404, 0, started)
                return

            token, filename = segs[1], segs[2]
            item = state.files_by_token.get(token)
            if item is None or item.name != filename:
                self.send_error(403, "forbidden")
                self._record("GET", 403, 0, started, token=token)
                return

            data = item.path.read_bytes()
            if len(data) > item.max_bytes:
                self.send_error(413, "too large")
                self._record("GET", 413, 0, started, token=token, name=filename)
                return

            body = data
            self.send_response(200)
            self.send_header("Content-Type", item.content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Probe-Marker", item.marker)
            self.end_headers()
            self.wfile.write(body)
            self._record("GET", 200, len(body), started, token=token, name=filename)

        def do_HEAD(self) -> None:  # noqa: N802
            # Allow HEAD for probes; same auth as GET but no body.
            started = time.monotonic()
            parts = urlsplit(self.path)
            path = unquote(parts.path)
            segs = [s for s in path.split("/") if s]
            if len(segs) != 3 or segs[0] != "t":
                self.send_error(404, "not found")
                self._record("HEAD", 404, 0, started)
                return
            token, filename = segs[1], segs[2]
            item = state.files_by_token.get(token)
            if item is None or item.name != filename:
                self.send_error(403, "forbidden")
                self._record("HEAD", 403, 0, started, token=token)
                return
            size = item.path.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", item.content_type)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self._record("HEAD", 200, 0, started, token=token, name=filename)

    return Handler


def start_server(
    host: str,
    port: int,
    state: ServerState,
) -> tuple[ThreadingHTTPServer, threading.Thread]:
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    thread = threading.Thread(target=httpd.serve_forever, name="probe-http", daemon=True)
    thread.start()
    return httpd, thread


def dump_events(state: ServerState) -> list[dict]:
    with state.lock:
        return [ev.__dict__.copy() for ev in state.events]
