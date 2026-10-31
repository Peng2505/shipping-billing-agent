"""Start 127.0.0.1 token file gateway + Cloudflare Quick Tunnel (exam/demo only).

Writes output/local_tunnel/status.json with public HTTPS URL and PIDs.
Does not start Streamlit.

Usage:
  .\\.venv\\Scripts\\python.exe scripts\\local_tunnel\\start_gateway.py
"""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from billing_agent.services.local_tunnel_gateway import GatewayState, purge_expired, start_gateway

OUT = ROOT / "output" / "local_tunnel"
STATUS = OUT / "status.json"
PID_FILE = OUT / "gateway.pids.json"
TOOLS = ROOT / "tools"
_IS_WIN = os.name == "nt" or sys.platform.startswith("win")
CLOUDFLARED = TOOLS / ("cloudflared.exe" if _IS_WIN else "cloudflared")
DEFAULT_PORT = int(os.getenv("LOCAL_TUNNEL_PORT", "8765"))


def _wait_tunnel_url(
    log_path: Path,
    proc: subprocess.Popen,
    log_fh,
    timeout_s: float = 90.0,
) -> str:
    """Poll cloudflared log file (flush writer so Windows readers see bytes)."""
    pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
    deadline = time.monotonic() + timeout_s
    pos = 0
    buf = ""
    while time.monotonic() < deadline:
        try:
            log_fh.flush()
            os.fsync(log_fh.fileno())
        except OSError:
            pass
        if proc.poll() is not None and pos == 0 and not log_path.exists():
            break
        if log_path.exists():
            data = log_path.read_bytes()
            if len(data) > pos:
                chunk = data[pos:].decode("utf-8", errors="replace")
                pos = len(data)
                buf += chunk
                m = pattern.search(buf)
                if m:
                    return m.group(0).rstrip("/")
        time.sleep(0.2)
    raise RuntimeError(f"tunnel URL not found; log tail:\n{buf[-2000:]}")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if not CLOUDFLARED.exists():
        print(f"ERROR: missing {CLOUDFLARED}. Download cloudflared into tools/ first.")
        return 1

    admin_token = os.getenv("LOCAL_TUNNEL_ADMIN_TOKEN") or secrets.token_urlsafe(32)
    port = DEFAULT_PORT
    state = GatewayState(admin_token=admin_token, max_upload_bytes=20 * 1024 * 1024)
    httpd, _thread = start_gateway("127.0.0.1", port, state)

    def janitor() -> None:
        while True:
            time.sleep(60)
            purge_expired(state)

    import threading

    threading.Thread(target=janitor, name="lt-janitor", daemon=True).start()

    cf_log = OUT / "cloudflared.log"
    try:
        if cf_log.exists():
            cf_log.unlink()
    except OSError:
        # Windows may still hold the previous cloudflared log handle briefly.
        cf_log = OUT / f"cloudflared_{int(time.time())}.log"
    log_fh = open(cf_log, "wb")
    tunnel = subprocess.Popen(
        [str(CLOUDFLARED), "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        cwd=str(ROOT),
    )
    try:
        public = _wait_tunnel_url(cf_log, tunnel, log_fh)
        print(f"Tunnel URL acquired: {public}", flush=True)
        # readiness
        import httpx

        ready = False
        last_err = None
        for attempt in range(1, 31):
            try:
                r = httpx.get(f"{public}/health", timeout=15, follow_redirects=True)
                if r.status_code == 200:
                    ready = True
                    print(f"Public health OK (attempt {attempt})", flush=True)
                    break
                last_err = f"http={r.status_code}"
            except Exception as exc:  # noqa: BLE001
                last_err = f"{type(exc).__name__}: {exc}"
            time.sleep(2)
        if not ready:
            raise RuntimeError(f"public tunnel health check failed: {last_err}")

        status = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "admin_base_url": f"http://127.0.0.1:{port}",
            "public_base_url": public,
            "admin_token": admin_token,
            "note": "Quick Tunnel for exam/demo only — URL changes each restart",
            "cloudflared_pid": tunnel.pid,
            "gateway_port": port,
        }
        STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        PID_FILE.write_text(
            json.dumps({"cloudflared_pid": tunnel.pid, "port": port}, indent=2),
            encoding="utf-8",
        )
        env_hint = ROOT / "output" / "local_tunnel" / "env.snippet"
        env_hint.write_text(
            "\n".join(
                [
                    "FILE_URL_PROVIDER=local_tunnel",
                    f"LOCAL_TUNNEL_ADMIN_BASE_URL=http://127.0.0.1:{port}",
                    f"LOCAL_TUNNEL_PUBLIC_BASE_URL={public}",
                    f"LOCAL_TUNNEL_ADMIN_TOKEN={admin_token}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        print("Local tunnel gateway READY", flush=True)
        print(f"  admin:  http://127.0.0.1:{port}", flush=True)
        print(f"  public: {public}", flush=True)
        print(f"  status: {STATUS}", flush=True)
        print(f"  env snippet: {env_hint}", flush=True)
        print("Press Ctrl+C to stop.", flush=True)
        while True:
            if tunnel.poll() is not None:
                raise RuntimeError("cloudflared exited unexpectedly")
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        try:
            tunnel.terminate()
            tunnel.wait(timeout=5)
        except Exception:
            try:
                tunnel.kill()
            except Exception:
                pass
        try:
            log_fh.close()
        except Exception:
            pass
        try:
            httpd.shutdown()
        except Exception:
            pass
        stopped = {
            "stopped_at": datetime.now(timezone.utc).isoformat(),
            "public_base_url": None,
            "note": "gateway stopped — do not reuse old Tunnel URL",
        }
        (OUT / "stopped.json").write_text(json.dumps(stopped, indent=2), encoding="utf-8")
        if STATUS.exists():
            STATUS.unlink()
        print("Stopped. Cleared status.json so stale Tunnel URLs cannot be reused.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
