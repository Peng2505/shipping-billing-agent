#!/bin/bash
set -euo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"
echo "=== 1_Install (macOS) ==="
echo "Project: $(pwd)"
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found. Install Python 3.11+ (python.org or brew install python@3.11)."
  read -r -p "Press Enter to close..."
  exit 1
fi

python3 -c 'import sys; raise SystemExit(0 if sys.version_info>=(3,11) else 1)' || {
  echo "ERROR: Need Python 3.11+."
  read -r -p "Press Enter to close..."
  exit 1
}

python3 "scripts/quick_start/install_env.py"
echo
echo "Done. Next: edit .env then double-click 2_Start.command"
read -r -p "Press Enter to close..."
