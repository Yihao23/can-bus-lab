"""candump -L / python-can Logger format:

    (1789297083.621266) vcan0 100#2412703C01000033
    (1789297083.621266) vcan0 100#2412703C01000033 R      <- newer can-utils add a direction flag
    (1789297083.621266) vcan0 18FEF100#0000000000000000    <- 29-bit: 8 hex digits
    (1789297083.621266) vcan0 7E0##1 0322F190...            <- CAN FD: '##' + flags nibble
    (1789297083.621266) vcan0 123#R                          <- remote frame
"""

from __future__ import annotations

import re

from ..models import Frame

LINE = re.compile(
    r"^\((?P<ts>\d+(?:\.\d+)?)\)\s+(?P<ch>\S+)\s+(?P<id>[0-9A-Fa-f]{3,8})"
    r"(?P<sep>#|##[0-9A-Fa-f])(?P<data>R|[0-9A-Fa-f]*)\s*(?P<dir>[RT])?\s*$"
)


def sniff(text: str) -> bool:
    for line in text.splitlines()[:20]:
        if LINE.match(line):
            return True
    return False


def parse(text: str) -> list[Frame]:
    frames: list[Frame] = []
    for line in text.splitlines():
        m = LINE.match(line)
        if not m:
            continue   # comments, blank lines, candump's own chatter
        id_hex = m["id"]
        remote = m["data"] == "R"
        data = b"" if remote else bytes.fromhex(m["data"])
        frames.append(Frame(
            index=len(frames),
            ts=float(m["ts"]),
            channel=m["ch"],
            can_id=int(id_hex, 16),
            data=data,
            extended=len(id_hex) > 3,
            fd=m["sep"].startswith("##"),
            remote=remote,
        ))
    return frames
