"""Exam demo orchestrator: preflight → LocalTunnel → Streamlit.

Does not auto-download cloudflared. Does not print API keys.
Reuses scripts/local_tunnel/start_gateway.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.demo.session_paths import (
    CLOUDFLARED,
    OUT_DEMO,
    OUT_LT,
    SESSION_FILE,
    STATUS_FILE,
    VENV_PYTHON,
    VENV_STREAMLIT,
)
from scripts.demo.stop_exam import main as stop_exam_main


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fail(msg: str, recovery: str) -> int:
    print(f"ERROR: {msg}", flush=True)
    print(f"RECOVERY: {recovery}", flush=True)
    return 1


def _mask_ok(name: str, present: bool) -> None:
    print(f"  [{('OK' if present else 'MISSING')}] {name}", flush=True)


def preflight() -> int:
    print("=== Preflight ===", flush=True)
    if not VENV_PYTHON.is_file():
        return _fail(
            f"venv Python not found: {VENV_PYTHON}",
            "python -m venv .venv && .\\.venv\\Scripts\\pip install -r requirements.txt",
        )
    _mask_ok("venv python", True)

    if not CLOUDFLARED.is_file():
        return _fail(
            f"cloudflared missing: {CLOUDFLARED}",
            "Run Quick Start/1_Install (downloads official Cloudflare release into tools/), "
            "or place cloudflared manually under tools/ (do not run unknown binaries).",
        )
    _mask_ok(f"tools/{CLOUDFLARED.name}", True)

    # Import check via venv
    check = subprocess.run(
        [
            str(VENV_PYTHON),
            "-c",
            "import streamlit,langchain,httpx,fitz,pydantic; print('imports_ok')",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if check.returncode != 0 or "imports_ok" not in (check.stdout or ""):
        return _fail(
            "required Python packages missing in .venv",
            ".\\.venv\\Scripts\\pip install -r requirements.txt",
        )
    _mask_ok("streamlit/langchain/httpx/pymupdf", True)

    env_path = ROOT / ".env"
    if not env_path.is_file():
        return _fail(
            ".env missing",
            "copy .env.example .env and set LLM_API_KEY / LLM_MODEL / LLM_BASE_URL "
            "(DeepSeek example in comments). Set FILE_URL_PROVIDER=local_tunnel.",
        )
    _mask_ok(".env present", True)

    # Parse .env without printing secrets
    vals: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        vals[k.strip()] = v.strip().strip('"').strip("'")

    llm_key = bool(vals.get("LLM_API_KEY"))
    llm_model = bool(vals.get("LLM_MODEL"))
    ocr_ep = bool(vals.get("OCR_ENDPOINT") or "https://gateway.pltplt.com/ai/process")
    provider = (vals.get("FILE_URL_PROVIDER") or "").strip().lower()
    _mask_ok("LLM_API_KEY set (value hidden)", llm_key)
    _mask_ok("LLM_MODEL set", llm_model)
    _mask_ok("OCR_ENDPOINT configured or default", ocr_ep)
    print(f"  [INFO] FILE_URL_PROVIDER={provider or '(empty→auto)'}", flush=True)
    if not llm_key or not llm_model:
        return _fail(
            "LLM not configured",
            "Edit .env: LLM_API_KEY, LLM_MODEL, LLM_BASE_URL "
            "(DeepSeek: https://api.deepseek.com , LLM_THINKING=disabled).",
        )
    if provider and provider != "local_tunnel":
        print(
            "  [WARN] Exam demo expects FILE_URL_PROVIDER=local_tunnel "
            f"(current={provider}). OSS/R2 OCR historically returned HTTP 504.",
            flush=True,
        )
    return 0


def _wait_status(timeout_s: float = 120.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if STATUS_FILE.is_file():
            try:
                data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
            except ValueError:
                data = {}
            public = str(data.get("public_base_url") or "")
            if public.startswith("https://") and data.get("admin_token"):
                return data
        time.sleep(0.5)
    raise TimeoutError("status.json with new public URL not ready")


def _health(admin: str, public: str) -> None:
    import httpx

    r = httpx.get(f"{admin.rstrip('/')}/health", timeout=10)
    if r.status_code != 200:
        raise RuntimeError(f"local health failed: {r.status_code}")
    r2 = httpx.get(f"{public.rstrip('/')}/health", timeout=30, follow_redirects=True)
    if r2.status_code != 200:
        raise RuntimeError(f"public health failed: {r2.status_code}")


def start_gateway() -> tuple[subprocess.Popen, dict]:
    OUT_LT.mkdir(parents=True, exist_ok=True)
    # Never reuse stale status
    if STATUS_FILE.is_file():
        STATUS_FILE.unlink()
        print("Cleared stale status.json", flush=True)

    log_path = OUT_DEMO / "gateway_stdout.log"
    OUT_DEMO.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "w", encoding="utf-8", errors="replace")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    # Force local_tunnel for this session without rewriting user's .env secrets
    env["FILE_URL_PROVIDER"] = "local_tunnel"

    proc = subprocess.Popen(
        [str(VENV_PYTHON), "-u", str(ROOT / "scripts" / "local_tunnel" / "start_gateway.py")],
        cwd=str(ROOT),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        env=env,
    )
    try:
        status = _wait_status(120.0)
    except Exception:
        proc.terminate()
        log_fh.close()
        raise
    # Record gateway python pid into gateway.pids.json for stop_exam
    pid_path = OUT_LT / "gateway.pids.json"
    try:
        existing = json.loads(pid_path.read_text(encoding="utf-8")) if pid_path.is_file() else {}
    except ValueError:
        existing = {}
    existing["gateway_pid"] = proc.pid
    existing["cloudflared_pid"] = status.get("cloudflared_pid")
    existing["port"] = status.get("gateway_port")
    pid_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return proc, status


def start_streamlit(port: int = 8501) -> subprocess.Popen:
    OUT_DEMO.mkdir(parents=True, exist_ok=True)
    log_fh = open(OUT_DEMO / "streamlit.log", "w", encoding="utf-8", errors="replace")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["FILE_URL_PROVIDER"] = "local_tunnel"
    # Prefer status.json values for tunnel (provider refreshes on put)
    if STATUS_FILE.is_file():
        st = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        env["LOCAL_TUNNEL_ADMIN_BASE_URL"] = st.get("admin_base_url") or env.get(
            "LOCAL_TUNNEL_ADMIN_BASE_URL", "http://127.0.0.1:8765"
        )
        env["LOCAL_TUNNEL_PUBLIC_BASE_URL"] = st.get("public_base_url") or ""
        env["LOCAL_TUNNEL_ADMIN_TOKEN"] = st.get("admin_token") or ""

    streamlit_bin = VENV_STREAMLIT if VENV_STREAMLIT.is_file() else None
    cmd = (
        [str(streamlit_bin), "run", "app.py", "--server.port", str(port), "--server.headless", "true"]
        if streamlit_bin
        else [
            str(VENV_PYTHON),
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.port",
            str(port),
            "--server.headless",
            "true",
        ]
    )
    return subprocess.Popen(cmd, cwd=str(ROOT), stdout=log_fh, stderr=subprocess.STDOUT, env=env)


def main() -> int:
    print(f"Shipping Billing AI — exam demo start ({_utc()})", flush=True)
    print(f"Project root: {ROOT}", flush=True)

    rc = preflight()
    if rc != 0:
        return rc

    print("=== Stopping previous exam session (this project only) ===", flush=True)
    stop_exam_main()

    print("=== Starting LocalTunnel gateway ===", flush=True)
    try:
        gw_proc, status = start_gateway()
    except Exception as exc:  # noqa: BLE001
        return _fail(
            f"LocalTunnel failed: {exc}",
            "1) Ensure port 8765 free  2) Check tools\\cloudflared.exe  "
            "3) Re-run Start-ExamDemo.ps1  4) See output\\demo_session\\gateway_stdout.log",
        )

    admin = status["admin_base_url"]
    public = status["public_base_url"]
    try:
        _health(admin, public)
    except Exception as exc:  # noqa: BLE001
        stop_exam_main()
        return _fail(
            f"Health check failed: {exc}",
            "Network/firewall may block Quick Tunnel. Retry Start-ExamDemo.ps1.",
        )
    print(f"  Local health OK:  {admin}/health", flush=True)
    print(f"  Public health OK: (new URL this session — not printed for README safety)", flush=True)
    print(f"  Public base host: {public.replace('https://', '')}", flush=True)

    print("=== Starting Streamlit ===", flush=True)
    port = int(os.getenv("STREAMLIT_PORT", "8501"))
    st_proc = start_streamlit(port)
    # Wait briefly for listen
    time.sleep(3)
    if st_proc.poll() is not None:
        stop_exam_main()
        return _fail(
            "Streamlit exited early",
            "See output\\demo_session\\streamlit.log ; ensure port 8501 free.",
        )

    session = {
        "generated_at": _utc(),
        "gateway_pid": gw_proc.pid,
        "cloudflared_pid": status.get("cloudflared_pid"),
        "streamlit_pid": st_proc.pid,
        "streamlit_url": f"http://localhost:{port}",
        "admin_base_url": admin,
        "public_base_url": public,
        "note": "Quick Tunnel exam/demo only — URL changes each restart",
    }
    OUT_DEMO.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")

    print("", flush=True)
    print("=== READY FOR HUMAN ACCEPTANCE ===", flush=True)
    print(f"Streamlit:  http://localhost:{port}", flush=True)
    print("LocalTunnel: running (status in output/local_tunnel/status.json)", flush=True)
    print("Synthetic samples: data/samples/synthetic_exam/", flush=True)
    print("Stop:  .\\scripts\\demo\\Stop-ExamDemo.ps1", flush=True)
    print("This window can stay open; services run in background.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
