#!/usr/bin/env bash
# Capture vcan0 three ways at once, for N seconds (default 30).
#   ./capture.sh <name> [seconds]
# Produces captures/<name>.log (candump, for project 04),
#          captures/<name>.pcap (for Wireshark),
#          captures/<name>.idstat (per-ID count / period / DLC summary).
set -euo pipefail
name="${1:?usage: capture.sh <name> [seconds]}"
secs="${2:-30}"
here="$(cd "$(dirname "$0")/.." && pwd)"
out="$here/captures/$name"

command -v candump >/dev/null || { echo "install can-utils first"; exit 1; }
ip link show vcan0 >/dev/null 2>&1 || { echo "no vcan0 — run setup/vcan-up.sh"; exit 1; }

echo "capturing vcan0 for ${secs}s -> $out.{log,pcap,idstat}"
# -L : candump's own log format, with absolute timestamps; project 04 reads it.
timeout "$secs" candump -L vcan0 > "$out.log" &
# tcpdump/tshark both understand SocketCAN link type; Wireshark decodes the raw frames
# and, with "Decode As" -> ISO-TP / UDS, the diagnostics on 0x7E0/0x7E8.
if command -v tshark >/dev/null; then
  timeout "$secs" tshark -i vcan0 -w "$out.pcap" -q 2>/dev/null &
fi
wait || true
python3 "$here/tools/idstat.py" "$out.log" | tee "$out.idstat"
