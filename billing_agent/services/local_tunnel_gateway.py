"""127.0.0.1-only token file gateway for Cloudflare Quick Tunnel.

Public path:  GET  /t/<access_token>/<object_id>
Admin path:   PUT|DELETE /admin/objects/<object_id>  (Bearer LOCAL_TUNNEL_ADMIN_TOKEN)
Health:       GET  /health

No directory listing. Keys must be hex object ids with allowed suffixes.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

logger = logging.getLogger(__name__)

_OBJECT_ID = re.compile(r"^[a-f0-9]{16,64}\.(pdf|png|jpg|jpeg|tif|tiff)$", re.I)
_ALLOWED_SUFFIX = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


@dataclass
class StoredObject:
    object_id: str
    data: bytes
    content_type: str
    access_token: str
    expires_at: float  # epoch seconds
    path: Path | None = None


@dataclass
class GatewayState:
    admin_token: str
    max_upload_bytes: int
    objects: dict[str, StoredObject] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    access_log: list[dict[str, Any]] = field(default_factory=list)


def is_valid_object_id(object_id: str) -> bool:
    if not object_id or ".." in object_id or "/" in object_id or "\\" in object_id:
        return False
    return bool(_OBJECT_ID.match(object_id))


def make_handler(state: GatewayState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:
            return

        def _json(self, code: int, body: dict[str, Any]) -> None:
            raw = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _record(self, **kwargs: Any) -> None:
            ev = {"ts": datetime.now(timezone.utc).isoformat(), **kwargs}
            with state.lock:
                state.access_log.append(ev)
                if len(state.access_log) > 500:
                    del state.access_log[:-200]

        def _require_admin(self) -> bool:
            header = self.headers.get("Authorization") or ""
            expected = f"Bearer {state.admin_token}"
            if not state.admin_token or header != expected:
                self._json(401, {"error": "unauthorized"})
                self._record(method=self.command, path=self.path, status=401)
                return False
            return True

        def do_GET(self) -> None:  # noqa: N802
            parts = urlsplit(self.path)
            path = unquote(parts.path)
            if path == "/health":
                self._json(200, {"ok": True, "service": "local_tunnel_gateway"})
                return
            segs = [s for s in path.split("/") if s]
            if len(segs) == 3 and segs[0] == "t":
                token, object_id = segs[1], segs[2]
                with state.lock:
                    obj = state.objects.get(object_id)
                if obj is None:
                    self._json(404, {"error": "not_found"})
                    self._record(method="GET", path=path, status=404, object_id=object_id)
                    return
                now = time.time()
                if now > obj.expires_at or token != obj.access_token:
                    self._json(401 if now > obj.expires_at else 403, {"error": "forbidden"})
                    self._record(method="GET", path=path, status=401, object_id=object_id)
                    return
                data = obj.data
                self.send_response(200)
                self.send_header("Content-Type", obj.content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                self._record(
                    method="GET",
                    path=path,
                    status=200,
                    object_id=object_id,
                    bytes=len(data),
                    user_agent=self.headers.get("User-Agent", ""),
                )
                return
            self._json(404, {"error": "not_found"})

        def do_PUT(self) -> None:  # noqa: N802
            parts = urlsplit(self.path)
            path = unquote(parts.path)
            segs = [s for s in path.split("/") if s]
            if not (len(segs) == 3 and segs[0] == "admin" and segs[1] == "objects"):
                self._json(404, {"error": "not_found"})
                return
            if not self._require_admin():
                return
            object_id = segs[2]
            if not is_valid_object_id(object_id):
                self._json(400, {"error": "invalid_object_id"})
                return
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0 or length > state.max_upload_bytes:
                self._json(413, {"error": "too_large"})
                return
            data = self.rfile.read(length)
            access_token = self.headers.get("X-Access-Token") or ""
            expires_at = float(self.headers.get("X-Expires-At") or "0")
            content_type = self.headers.get("Content-Type") or "application/octet-stream"
            if len(access_token) < 16 or expires_at <= time.time():
                self._json(400, {"error": "invalid_token_meta"})
                return
            stored = StoredObject(
                object_id=object_id,
                data=data,
                content_type=content_type,
                access_token=access_token,
                expires_at=expires_at,
            )
            with state.lock:
                state.objects[object_id] = stored
            self._json(200, {"ok": True, "object_id": object_id})
            self._record(method="PUT", path=path, status=200, object_id=object_id, bytes=len(data))

        def do_DELETE(self) -> None:  # noqa: N802
            parts = urlsplit(self.path)
            path = unquote(parts.path)
            segs = [s for s in path.split("/") if s]
            if not (len(segs) == 3 and segs[0] == "admin" and segs[1] == "objects"):
                self._json(404, {"error": "not_found"})
                return
            if not self._require_admin():
                return
            object_id = segs[2]
            with state.lock:
                state.objects.pop(object_id, None)
            self._json(200, {"ok": True})
            self._record(method="DELETE", path=path, status=200, object_id=object_id)

    return Handler


def start_gateway(
    host: str,
    port: int,
    state: GatewayState,
) -> tuple[ThreadingHTTPServer, threading.Thread]:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("local tunnel gateway must bind to 127.0.0.1 only")
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    thread = threading.Thread(target=httpd.serve_forever, name="local-tunnel-gw", daemon=True)
    thread.start()
    return httpd, thread


def purge_expired(state: GatewayState) -> int:
    now = time.time()
    removed = 0
    with state.lock:
        dead = [k for k, v in state.objects.items() if v.expires_at <= now]
        for k in dead:
            state.objects.pop(k, None)
            removed += 1
    return removed
