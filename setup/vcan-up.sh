#!/usr/bin/env bash
# Create vcan0 (and load the ISO-TP module). Needs root. Idempotent.
#   sudo setup/vcan-up.sh [vcan0]
set -euo pipefail
dev="${1:-vcan0}"
modprobe vcan
modprobe can-isotp || echo "can-isotp module not available; python can-isotp still works"
if ! ip link show "$dev" >/dev/null 2>&1; then
  ip link add dev "$dev" type vcan
fi
ip link set "$dev" up
ip -details link show "$dev" | head -3
echo "$dev is up. Try:  candump $dev   /   cansend $dev 123#DEADBEEF"
