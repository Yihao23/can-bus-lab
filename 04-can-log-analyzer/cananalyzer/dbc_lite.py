"""The 5 % of the DBC grammar this tool needs: BO_, SG_, BA_ GenMsgCycleTime
and E2EDataId. Not a DBC library — cantools is one — but a diagnostic tool on
a rig cannot pip install, so this reads enough to know what *should* be on
the bus.
只读 DBC 语法的 5%。不是 DBC 库(cantools 才是)，但试验台上的诊断工具没法 pip install，
所以自己读到"够知道总线上应该有什么"为止。
"""

from __future__ import annotations

import re

from .models import MessageDef, Signal

BO = re.compile(r"^BO_\s+(\d+)\s+(\w+)\s*:\s*(\d+)\s+(\w+)")
SG = re.compile(
    r'^\s*SG_\s+(\w+)\s*(?:m\d+|M)?\s*:\s*(\d+)\|(\d+)@([01])([+-])\s*'
    r'\(([-\d.eE]+),([-\d.eE]+)\)\s*\[[^\]]*\]\s*"([^"]*)"'
)
BA_INT = re.compile(r'^BA_\s+"(GenMsgCycleTime|E2EDataId)"\s+BO_\s+(\d+)\s+(\d+)\s*;')

DBC_EXTENDED_FLAG = 0x80000000   # DBC marks 29-bit IDs by setting bit 31


def load(text: str) -> dict[int, MessageDef]:
    messages: dict[int, MessageDef] = {}
    current: MessageDef | None = None
    for line in text.splitlines():
        m = BO.match(line)
        if m:
            raw_id = int(m[1])
            can_id = raw_id & ~DBC_EXTENDED_FLAG
            current = MessageDef(can_id=can_id, name=m[2], dlc=int(m[3]), sender=m[4])
            messages[can_id] = current
            continue
        m = SG.match(line)
        if m and current is not None:
            current.signals.append(Signal(
                name=m[1], start=int(m[2]), length=int(m[3]),
                little_endian=m[4] == "1", signed=m[5] == "-",
                factor=float(m[6]), offset=float(m[7]), unit=m[8],
            ))
            continue
        m = BA_INT.match(line)
        if m:
            target = messages.get(int(m[2]) & ~DBC_EXTENDED_FLAG)
            if target is None:
                continue
            if m[1] == "GenMsgCycleTime":
                target.cycle_ms = float(m[3]) or None
            else:
                target.e2e_data_id = int(m[3])
    return messages


def load_file(path: str) -> dict[int, MessageDef]:
    with open(path, encoding="utf-8", errors="replace") as f:
        return load(f.read())


def decode_signal(sig: Signal, data: bytes) -> float | None:
    """Physical value of one signal, or None if the frame is too short."""
    if sig.little_endian:
        raw = int.from_bytes(data, "little")
        if sig.start + sig.length > len(data) * 8:
            return None
        raw = (raw >> sig.start) & ((1 << sig.length) - 1)
    else:
        # TODO(you) — project 04, day 12
        # Motorola. The DBC start bit is the MSB of the signal, numbered in
        # the "sawtooth" scheme: bit 7 of byte 0 is 7, bit 0 of byte 1 is 8.
        # Convert the start bit to a (byte, bit) position, walk `length` bits
        # towards the LSB crossing byte boundaries downwards, and build `raw`.
        # Test it against BODY_STATUS.OutsideTemp in samples/lab_vehicle.dbc:
        # raw byte 1 = 0xE7 must decode to -12.5. There is a commented test.
        # Motorola 字节序。DBC 起始位是信号的 MSB，用"锯齿"编号。
        return None
    if sig.signed and raw & (1 << (sig.length - 1)):
        raw -= 1 << sig.length
    return raw * sig.factor + sig.offset


def decode_message(msg: MessageDef, data: bytes) -> dict[str, float]:
    out = {}
    for sig in msg.signals:
        v = decode_signal(sig, data)
        if v is not None:
            out[sig.name] = v
    return out
