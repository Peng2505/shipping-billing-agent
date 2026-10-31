"""Stop only processes started by this project's exam demo session.

Does not kill unrelated cloudflared or Python processes.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.demo.session_paths import OUT_DEMO, OUT_LT, SESSION_FILE, STATUS_FILE


def _kill(pid: int, label: str) -> None:
    if pid <= 0:
        return
    print(f"Stopping {label} pid={pid}")
    if os.name == "nt":
        os.system(f"taskkill /PID {pid} /T /F >NUL 2>&1")
    else:
        try:
            os.kill(pid, 15)
        except OSError:
            pass


def _pids_from_session() -> dict[str, int]:
    if not SESSION_FILE.is_file():
        return {}
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    out: dict[str, int] = {}
    for key in ("gateway_pid", "cloudflared_pid", "streamlit_pid"):
        val = data.get(key)
        if val is not None:
            try:
                out[key] = int(val)
            except (TypeError, ValueError):
                pass
    return out


def _pids_from_status() -> dict[str, int]:
    out: dict[str, int] = {}
    for name in ("status.json", "gateway.pids.json"):
        path = OUT_LT / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if data.get("cloudflared_pid"):
            out["cloudflared_pid"] = int(data["cloudflared_pid"])
        if data.get("gateway_pid"):
            out["gateway_pid"] = int(data["gateway_pid"])
    return out


def main() -> int:
    pids = {**_pids_from_status(), **_pids_from_session()}
    # Stop Streamlit first, then gateway (owns cloudflared cleanup ideally), then cloudflared.
    order = ("streamlit_pid", "gateway_pid", "cloudflared_pid")
    seen: set[int] = set()
    for key in order:
        pid = pids.get(key)
        if pid and pid not in seen:
            seen.add(pid)
            _kill(pid, key)
    time.sleep(1)

    for path in (
        STATUS_FILE,
        OUT_LT / "env.snippet",
        OUT_LT / "gateway.pids.json",
        SESSION_FILE,
    ):
        if path.is_file():
            path.unlink()
            print(f"Removed {path.relative_to(ROOT)}")

    OUT_DEMO.mkdir(parents=True, exist_ok=True)
    (OUT_DEMO / "stopped.json").write_text(
        json.dumps(
            {
                "note": "exam demo stopped — do not reuse old Tunnel URL",
                "killed_pids": sorted(seen),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Exam demo stopped. Stale Tunnel status cleared.")
    print("Recovery: re-run scripts\\demo\\Start-ExamDemo.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
