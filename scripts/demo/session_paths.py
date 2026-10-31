"""Shared paths for exam demo session (gateway + Streamlit PIDs)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_LT = ROOT / "output" / "local_tunnel"
OUT_DEMO = ROOT / "output" / "demo_session"
SESSION_FILE = OUT_DEMO / "session.json"
STATUS_FILE = OUT_LT / "status.json"

_IS_WIN = os.name == "nt" or sys.platform.startswith("win")
CLOUDFLARED = ROOT / "tools" / ("cloudflared.exe" if _IS_WIN else "cloudflared")
if _IS_WIN:
    VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
    VENV_STREAMLIT = ROOT / ".venv" / "Scripts" / "streamlit.exe"
else:
    VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
    VENV_STREAMLIT = ROOT / ".venv" / "bin" / "streamlit"
