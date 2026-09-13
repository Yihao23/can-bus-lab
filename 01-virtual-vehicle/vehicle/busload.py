"""Bus load estimation for classic CAN.

The question behind it / 背后的面试题:
"Your 500 kbit/s bus carries 40 messages at 10 ms. Is that OK?"
Nobody answers that from memory; they compute it. So here is the computation.

Frame length on the wire, standard (11-bit) identifier, no bit stuffing:
    SOF 1 + ID 11 + RTR 1 + IDE 1 + r0 1 + DLC 4 + data 8n + CRC 15 + CRC del 1
    + ACK 2 + EOF 7 + IFS 3  = 47 + 8n
Extended (29-bit) adds SRR 1 + 18 more ID bits + r1 1 = 67 + 8n.

Bit stuffing: after 5 equal bits one opposite bit is inserted. It applies from
SOF to the CRC field (not to CRC delimiter, ACK, EOF, IFS). Worst case is one
stuff bit every 4 bits of the stuffed region, which is what a bus designer
budgets for. The average with random data is far lower, roughly one per 12.
"""

from __future__ import annotations

from dataclasses import dataclass

OVERHEAD_STD = 47
OVERHEAD_EXT = 67
UNSTUFFED_TAIL = 1 + 2 + 7 + 3  # CRC delimiter, ACK, EOF, IFS


def frame_bits(dlc: int, extended: bool = False, worst_case_stuffing: bool = True) -> int:
    if not 0 <= dlc <= 8:
        raise ValueError("classic CAN carries 0..8 data bytes")
    base = (OVERHEAD_EXT if extended else OVERHEAD_STD) + 8 * dlc
    if not worst_case_stuffing:
        return base
    stuffable = base - UNSTUFFED_TAIL
    return base + (stuffable - 1) // 4


@dataclass(frozen=True)
class CyclicMessage:
    name: str
    dlc: int
    cycle_ms: float
    extended: bool = False

    def bits_per_second(self, worst_case: bool = True) -> float:
        return frame_bits(self.dlc, self.extended, worst_case) * (1000.0 / self.cycle_ms)


def bus_load(messages: list[CyclicMessage], bitrate: int, worst_case: bool = True) -> float:
    """Fraction 0.0..N of the bus consumed. Above ~0.7 the low-priority messages
    start missing their deadlines under bursts; the usual design ceiling."""
    return sum(m.bits_per_second(worst_case) for m in messages) / bitrate
