#!/usr/bin/env bash
# One venv for all four projects, plus the apt packages the vcan demos need.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r 01-virtual-vehicle/requirements.txt -r 02-uds-diagnostics/requirements.txt
echo "venv ready: source .venv/bin/activate"
if ! command -v candump >/dev/null; then
  echo "can-utils missing. Install it for the vcan demos:  sudo apt install can-utils"
fi
