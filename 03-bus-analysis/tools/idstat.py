#!/usr/bin/env python3
"""Per-ID statistics from a candump log. Standard library only.

    python3 idstat.py capture.log

The first thing to do with an unknown bus: how many IDs, which are periodic
(and at what period), which are event-driven, which bytes ever change.
拿到一条陌生总线的第一步: 有多少 ID、哪些是周期的(周期多少)、哪些是事件触发的、
哪些字节曾经变过。
"""

import re
import statistics
import sys
from collections import defaultdict

LINE = re.compile(r"^\((?P<ts>[\d.]+)\)\s+(?P<if>\S+)\s+(?P<id>[0-9A-Fa-f]+)#(?P<data>[0-9A-Fa-f]*)")


def main(path):
    ts_by_id = defaultdict(list)
    data_by_id = defaultdict(list)
    with open(path) as f:
        for line in f:
            m = LINE.match(line)
            if not m:
                continue
            ts_by_id[m["id"]].append(float(m["ts"]))
            data_by_id[m["id"]].append(bytes.fromhex(m["data"]))
    print(f"{'id':>8} {'count':>6} {'period_ms':>10} {'jitter_ms':>10} {'dlc':>4}  changing bytes")
    for cid in sorted(ts_by_id, key=lambda x: int(x, 16)):
        ts = ts_by_id[cid]
        gaps = [b - a for a, b in zip(ts, ts[1:])]
        period = statistics.median(gaps) * 1000 if gaps else float("nan")
        jitter = statistics.pstdev(gaps) * 1000 if len(gaps) > 1 else 0.0
        frames = data_by_id[cid]
        dlcs = {len(d) for d in frames}
        changing = sorted({i for d in frames for i in range(len(d)) if d[i] != frames[0][i] if i < len(frames[0])})
        kind = "event" if gaps and jitter > period / 2 else "cyclic"
        print(f"{cid:>8} {len(ts):>6} {period:>10.1f} {jitter:>10.1f} {'/'.join(map(str, sorted(dlcs))):>4}  "
              f"{changing if changing else '-'}  {kind}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) == 2 else print(__doc__))
