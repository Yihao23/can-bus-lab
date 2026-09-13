from __future__ import annotations

import argparse
import sys

from . import dbc_lite
from .parsers import candump
from .render import RENDERERS
from .rules import Context, run_all


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="cananalyzer", description="analyze a candump log")
    p.add_argument("log")
    p.add_argument("--dbc", help="DBC for names, DLCs, cycle times and E2E DataIDs")
    p.add_argument("--format", choices=sorted(RENDERERS), default="text")
    p.add_argument("-o", "--output")
    p.add_argument("--bitrate", type=int, default=500_000)
    p.add_argument("--busload-limit", type=float, default=0.70)
    p.add_argument("--p2", type=float, default=50.0, help="UDS P2server_max in ms")
    p.add_argument("--p2-star", type=float, default=5000.0, help="UDS P2*server_max in ms")
    p.add_argument("--fail-on-error", action="store_true", help="exit 1 if any ERROR finding")
    args = p.parse_args(argv)

    with open(args.log, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if not candump.sniff(text):
        print(f"{args.log}: not a candump log (expected lines like '(123.456) vcan0 100#DEADBEEF')", file=sys.stderr)
        return 2
    frames = candump.parse(text)
    if not frames:
        print(f"{args.log}: no frames", file=sys.stderr)
        return 2
    dbc = dbc_lite.load_file(args.dbc) if args.dbc else {}
    ctx = Context(frames=frames, dbc=dbc, bitrate=args.bitrate, busload_limit=args.busload_limit,
                  p2_ms=args.p2, p2_star_ms=args.p2_star)
    findings = run_all(ctx, fold=args.format != "json")
    out = RENDERERS[args.format](ctx, findings)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"wrote {args.output} ({len(out)} bytes, {len(findings)} findings)")
    else:
        sys.stdout.write(out)
    if args.fail_on_error and any(f.severity == "ERROR" for f in findings):
        return 1
    return 0
