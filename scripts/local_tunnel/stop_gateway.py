"""Stop local tunnel gateway / cloudflared processes recorded in status files."""

from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "local_tunnel"


def _kill(pid: int) -> None:
    if pid <= 0:
        return
    try:
        if os.name == "nt":
            os.system(f"taskkill /PID {pid} /F >NUL 2>&1")
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def main() -> int:
    pids = []
    for name in ("gateway.pids.json", "status.json"):
        path = OUT / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if data.get("cloudflared_pid"):
            pids.append(int(data["cloudflared_pid"]))
    for pid in sorted(set(pids)):
        print(f"stopping pid {pid}")
        _kill(pid)
    for f in ("status.json", "env.snippet"):
        p = OUT / f
        if p.exists():
            p.unlink()
            print(f"removed {p}")
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
