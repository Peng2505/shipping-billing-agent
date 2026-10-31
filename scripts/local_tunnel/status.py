"""Print local tunnel gateway status (no secrets printed in full)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "output" / "local_tunnel" / "status.json"


def main() -> int:
    if not STATUS.is_file():
        print("STATUS: not_running (no status.json)")
        print("Start: .\\.venv\\Scripts\\python.exe scripts\\local_tunnel\\start_gateway.py")
        return 1
    data = json.loads(STATUS.read_text(encoding="utf-8"))
    public = data.get("public_base_url")
    admin = data.get("admin_base_url")
    token = data.get("admin_token") or ""
    print(f"public_base_url: {public}")
    print(f"admin_base_url:  {admin}")
    print(f"admin_token:     set(len={len(token)})")
    try:
        r = httpx.get(f"{admin}/health", timeout=3)
        print(f"admin_health:    HTTP {r.status_code} {r.text[:80]}")
    except Exception as exc:
        print(f"admin_health:    FAILED {type(exc).__name__}")
        return 2
    try:
        r = httpx.get(f"{public}/health", timeout=15, follow_redirects=True)
        print(f"public_health:   HTTP {r.status_code}")
    except Exception as exc:
        print(f"public_health:   FAILED {type(exc).__name__}")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
