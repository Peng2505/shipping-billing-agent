"""One-shot env bootstrap for Quick Start (Windows / macOS).

Creates .venv, installs requirements.txt, downloads official cloudflared into
tools/, and copies .env.example → .env when missing.

Does not print secret values. Downloads only from Cloudflare GitHub releases.
"""

from __future__ import annotations

import os
import platform
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
REQ = ROOT / "requirements.txt"
ENV_EXAMPLE = ROOT / ".env.example"
ENV_FILE = ROOT / ".env"

_CF_BASE = "https://github.com/cloudflare/cloudflared/releases/latest/download"


def _is_windows() -> bool:
    return os.name == "nt" or sys.platform.startswith("win")


def _venv_python() -> Path:
    if _is_windows():
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


def _venv_pip() -> list[str]:
    return [str(_venv_python()), "-m", "pip"]


def _cloudflared_path() -> Path:
    return TOOLS / ("cloudflared.exe" if _is_windows() else "cloudflared")


def _system_python_cmd() -> list[str]:
    """Return argv prefix that runs Python 3.11+."""
    if _is_windows() and shutil.which("py"):
        try:
            out = subprocess.check_output(
                ["py", "-3", "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            major, minor = (int(x) for x in out.split("."))
            if (major, minor) >= (3, 11):
                return ["py", "-3"]
        except (subprocess.CalledProcessError, ValueError, OSError):
            pass

    for name in ("python3", "python"):
        path = shutil.which(name)
        if not path:
            continue
        try:
            out = subprocess.check_output(
                [path, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            major, minor = (int(x) for x in out.split("."))
            if (major, minor) >= (3, 11):
                return [path]
        except (subprocess.CalledProcessError, ValueError, OSError):
            continue

    raise SystemExit(
        "ERROR: Python 3.11+ not found. Install from https://www.python.org/downloads/ "
        "and re-run 1_Install."
    )


def step_venv() -> None:
    py = _venv_python()
    if py.is_file():
        print(f"[OK] venv exists: {py}")
        return
    cmd = _system_python_cmd() + ["-m", "venv", str(ROOT / ".venv")]
    print(f"[..] creating venv with: {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=str(ROOT))
    if not py.is_file():
        raise SystemExit(f"ERROR: venv python missing after create: {py}")
    print(f"[OK] venv created: {py}")


def step_deps() -> None:
    if not REQ.is_file():
        raise SystemExit(f"ERROR: missing {REQ}")
    print("[..] upgrading pip")
    subprocess.check_call(_venv_pip() + ["install", "--upgrade", "pip"], cwd=str(ROOT))
    print(f"[..] pip install -r {REQ.name}")
    subprocess.check_call(_venv_pip() + ["install", "-r", str(REQ)], cwd=str(ROOT))
    print("[OK] Python dependencies installed")


def _download(url: str, dest: Path) -> None:
    print(f"[..] downloading {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        url, headers={"User-Agent": "shipping-billing-agent-quickstart"}
    )
    with urllib.request.urlopen(req, context=ctx, timeout=180) as resp, dest.open("wb") as fh:
        shutil.copyfileobj(resp, fh)


def step_cloudflared() -> None:
    target = _cloudflared_path()
    if target.is_file() and target.stat().st_size > 1_000_000:
        print(f"[OK] cloudflared already present: {target}")
        return

    machine = platform.machine().lower()
    TOOLS.mkdir(parents=True, exist_ok=True)

    if _is_windows():
        url = f"{_CF_BASE}/cloudflared-windows-amd64.exe"
        _download(url, target)
    else:
        asset = (
            "cloudflared-darwin-arm64.tgz"
            if machine in {"arm64", "aarch64"}
            else "cloudflared-darwin-amd64.tgz"
        )
        url = f"{_CF_BASE}/{asset}"
        with tempfile.TemporaryDirectory() as tmp:
            tgz = Path(tmp) / asset
            _download(url, tgz)
            with tarfile.open(tgz, "r:gz") as tar:
                tar.extractall(path=tmp)
            matches = [m for m in Path(tmp).rglob("cloudflared") if m.is_file()]
            if not matches:
                raise SystemExit("ERROR: cloudflared binary not found inside archive")
            shutil.copy2(matches[0], target)
        os.chmod(target, 0o755)

    if not target.is_file() or target.stat().st_size < 1_000_000:
        raise SystemExit(f"ERROR: cloudflared download looks invalid: {target}")
    print(f"[OK] cloudflared ready: {target}")
    print("     Source: Cloudflare GitHub Releases (official).")


def step_env() -> None:
    if ENV_FILE.is_file():
        print("[OK] .env already exists (secrets not printed)")
        return
    if not ENV_EXAMPLE.is_file():
        raise SystemExit(f"ERROR: missing {ENV_EXAMPLE}")
    shutil.copy2(ENV_EXAMPLE, ENV_FILE)
    print("[OK] created .env from .env.example")
    print("     Edit .env and set LLM_API_KEY / LLM_MODEL / LLM_BASE_URL before starting.")
    print("     FILE_URL_PROVIDER=local_tunnel is already the exam default.")


def main() -> int:
    print("=== Quick Start install ===")
    print(f"Project root: {ROOT}")
    print(f"Platform: {sys.platform} / {platform.machine()}")
    try:
        step_venv()
        step_deps()
        step_cloudflared()
        step_env()
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: command failed with exit {exc.returncode}")
        return exc.returncode or 1
    print("")
    print("Install finished.")
    print("Next: edit .env (LLM_API_KEY), then run 2_Start.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
