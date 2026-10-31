#!/bin/bash
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"
echo "=== 2_Start (macOS) ==="
echo "Project: $(pwd)"
echo

if [[ ! -x ".venv/bin/python" ]]; then
  echo "ERROR: .venv missing. Run 1_Install.command first."
  read -r -p "Press Enter to close..."
  exit 1
fi

.venv/bin/python -u "scripts/demo/start_exam.py"
echo
echo "UI: http://localhost:8501"
echo "Stop later with 3_Stop.command"
read -r -p "Press Enter to close..."
