"""ISO 15765-2 reassembly from raw frames, per CAN ID.

Four frame types, identified by the high nibble of byte 0:
    0 SF  single frame        low nibble = length (1..7)
    1 FF  first frame         12-bit length in the low nibble + byte 1, then 6 data bytes
    2 CF  consecutive frame   low nibble = sequence number 1..15, wrapping to 0
    3 FC  flow control        low nibble = flow status (0 CTS, 1 Wait, 2 Overflow), byte 1 BS, byte 2 STmin
This module does not know or care which side is tester and which is ECU.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Frame

SF, FF, CF, FC = 0, 1, 2, 3


@dataclass
class IsoTpMessage:
    can_id: int
    ts_first: float
    ts_last: float
    payload: bytes
    frames: list[int]            # frame indices that built it
    complete: bool = True
    error: str | None = None


@dataclass
class FlowControl:
    can_id: int
    ts: float
    frame_index: int
    status: int
    block_size: int
    st_min: int


@dataclass
class _Assembly:
    expected_len: int
    payload: bytearray
    next_sn: int
    ts_first: float
    frames: list[int] = field(default_factory=list)


@dataclass
class IsoTpResult:
    messages: list[IsoTpMessage]
    flow_controls: list[FlowControl]


def reassemble(frames: list[Frame], ids: set[int] | None = None) -> IsoTpResult:
    """`ids` restricts to diagnostic IDs; None means every ID whose frames
    look like ISO-TP — which on a bus with random payloads will produce
    nonsense, so callers should pass the IDs."""
    messages: list[IsoTpMessage] = []
    fcs: list[FlowControl] = []
    open_: dict[int, _Assembly] = {}

    for fr in frames:
        if ids is not None and fr.can_id not in ids:
            continue
        if not fr.data:
            continue
        pci = fr.data[0] >> 4
        low = fr.data[0] & 0x0F

        if pci == SF:
            _abort(open_, fr.can_id, messages, "first frame never completed")
            length = low
            if length == 0 or length > len(fr.data) - 1:
                messages.append(IsoTpMessage(fr.can_id, fr.ts, fr.ts, bytes(fr.data[1:]), [fr.index], False,
                                             f"single frame length {length} does not fit DLC {len(fr.data)}"))
                continue
            messages.append(IsoTpMessage(fr.can_id, fr.ts, fr.ts, bytes(fr.data[1:1 + length]), [fr.index]))

        elif pci == FF:
            _abort(open_, fr.can_id, messages, "first frame never completed")
            length = (low << 8) | fr.data[1]
            open_[fr.can_id] = _Assembly(length, bytearray(fr.data[2:]), 1, fr.ts, [fr.index])

        elif pci == CF:
            asm = open_.get(fr.can_id)
            if asm is None:
                messages.append(IsoTpMessage(fr.can_id, fr.ts, fr.ts, bytes(fr.data[1:]), [fr.index], False,
                                             "consecutive frame without a first frame"))
                continue
            if low != asm.next_sn:
                asm.frames.append(fr.index)
                messages.append(IsoTpMessage(fr.can_id, asm.ts_first, fr.ts, bytes(asm.payload), asm.frames, False,
                                             f"consecutive frame sequence error: expected SN {asm.next_sn}, got {low}"))
                del open_[fr.can_id]
                continue
            asm.next_sn = (asm.next_sn + 1) & 0x0F
            asm.payload += fr.data[1:]
            asm.frames.append(fr.index)
            if len(asm.payload) >= asm.expected_len:
                messages.append(IsoTpMessage(fr.can_id, asm.ts_first, fr.ts, bytes(asm.payload[:asm.expected_len]), asm.frames))
                del open_[fr.can_id]

        elif pci == FC:
            fcs.append(FlowControl(fr.can_id, fr.ts, fr.index, low,
                                   fr.data[1] if len(fr.data) > 1 else 0,
                                   fr.data[2] if len(fr.data) > 2 else 0))

    for can_id in list(open_):
        _abort(open_, can_id, messages, "log ended mid-message")
    messages.sort(key=lambda m: m.ts_first)
    return IsoTpResult(messages, fcs)


def _abort(open_, can_id, messages, why):
    asm = open_.pop(can_id, None)
    if asm is not None:
        messages.append(IsoTpMessage(can_id, asm.ts_first, asm.ts_first, bytes(asm.payload), asm.frames, False, why))
