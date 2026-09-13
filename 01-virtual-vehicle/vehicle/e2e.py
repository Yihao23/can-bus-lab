"""End-to-end (E2E) protection: alive counter + CRC-8.

Why this exists / 为什么有这个文件:
CAN's own CRC-15 only protects a frame *on the wire*. It says nothing about a
sender whose software hung and keeps re-sending the same stale bytes, a gateway
that duplicated a frame, or a frame that arrived late. AUTOSAR E2E adds a
counter (detects loss, repetition, reordering) and an application-level CRC
over a data ID + payload (detects a frame that is valid CAN but belongs to a
different message or was corrupted before it reached the controller).
CAN 自带的 CRC-15 只保护"线上"这一段。发送方软件卡死后一直重发同一份旧数据、
网关复制了一帧、帧到得太晚 —— 这些它一个都看不出来。AUTOSAR E2E 加了计数器
(发现丢帧/重复/乱序) 和带 DataID 的应用层 CRC (发现"CAN 层合法但属于别的报文
或在到控制器前就坏了"的帧)。

The layout used here is a simplification of AUTOSAR E2E Profile 1:
    byte 6 low nibble : alive counter, 0..14, then wraps  (15 is never sent)
    byte 7            : CRC-8 SAE J1850 over [data_id] + bytes 0..6
"""

from __future__ import annotations

# CRC-8 SAE J1850: poly 0x1D, init 0xFF, no reflection, xorout 0xFF.
# Check value for b"123456789" is 0x4B — the test pins that.
_POLY = 0x1D


def _make_table() -> list[int]:
    table = []
    for byte in range(256):
        crc = byte
        for _ in range(8):
            crc = ((crc << 1) ^ _POLY) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
        table.append(crc)
    return table


_TABLE = _make_table()


def crc8_j1850(data: bytes, init: int = 0xFF) -> int:
    crc = init
    for b in data:
        crc = _TABLE[(crc ^ b) & 0xFF]
    return crc ^ 0xFF


COUNTER_BYTE = 6
CRC_BYTE = 7
COUNTER_MAX = 14  # 0..14 inclusive; 15 is reserved, same as Profile 1


def protect(payload: bytearray, data_id: int, counter: int) -> bytearray:
    """Write counter and CRC into an 8-byte payload, in place, and return it.

    Bits 4..7 of byte 6 are left untouched so a DBC can put a signal there.
    """
    if len(payload) != 8:
        raise ValueError("E2E layout assumes an 8-byte classic CAN frame")
    if not 0 <= counter <= COUNTER_MAX:
        raise ValueError(f"counter {counter} outside 0..{COUNTER_MAX}")
    payload[COUNTER_BYTE] = (payload[COUNTER_BYTE] & 0xF0) | counter
    payload[CRC_BYTE] = crc8_j1850(bytes([data_id]) + bytes(payload[:CRC_BYTE]))
    return payload


def next_counter(counter: int) -> int:
    return 0 if counter >= COUNTER_MAX else counter + 1


def crc_ok(payload: bytes, data_id: int) -> bool:
    if len(payload) != 8:
        return False
    return payload[CRC_BYTE] == crc8_j1850(bytes([data_id]) + bytes(payload[:CRC_BYTE]))


def counter_of(payload: bytes) -> int:
    return payload[COUNTER_BYTE] & 0x0F


class E2EReceiver:
    """Receiver-side check. One instance per protected message.

    `check()` returns one of:
        "ok"        counter advanced by exactly one and CRC matches
        "initial"   first frame ever seen — nothing to compare against
        "crc"       CRC mismatch; counter not evaluated
        "repeated"  same counter as last time (sender hung / frame duplicated)
        "lost"      counter jumped — one or more frames missing
        "wrong_seq" counter went backwards (reorder, or a replayed frame)
    """

    def __init__(self, data_id: int):
        self.data_id = data_id
        self.last_counter: int | None = None
        self.stats = {"ok": 0, "initial": 0, "crc": 0, "repeated": 0, "lost": 0, "wrong_seq": 0}

    def check(self, payload: bytes) -> str:
        if not crc_ok(payload, self.data_id):
            self.stats["crc"] += 1
            return "crc"
        counter = counter_of(payload)
        # TODO(you) — project 01, day 3
        # Implement the counter check. Rules to get right, in this order:
        #   1. first frame seen -> "initial", remember counter
        #   2. same counter as last -> "repeated"
        #   3. counter == next_counter(last) -> "ok"
        #   4. counter is 2..MaxDeltaCounter ahead -> "lost"  (Profile 1 tolerates
        #      a configurable number of lost frames; pick MaxDeltaCounter = 3 and
        #      say in the README why it is not 1 and not 14)
        #   5. anything else -> "wrong_seq"
        # Wrap-around 14 -> 0 must be "ok". Write the tests in
        # tests/test_e2e.py first; there is a commented block waiting for you.
        # 先写测试再写实现。14 -> 0 的回绕必须判为 "ok"。
        self.last_counter = counter
        self.stats["ok"] += 1
        return "ok"
