#!/bin/bash
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"
echo "=== 3_Stop (macOS) ==="
echo "Project: $(pwd)"
echo

if [[ -x ".venv/bin/python" ]]; then
  .venv/bin/python -u "scripts/demo/stop_exam.py"
else
  echo "WARNING: .venv missing; trying system python3"
  python3 -u "scripts/demo/stop_exam.py" || true
fi

echo
echo "Stopped this project's Streamlit / LocalTunnel session (if running)."
read -r -p "Press Enter to close..."
