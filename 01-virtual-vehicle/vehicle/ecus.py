"""The ECUs. Three senders, one receiver, each in its own thread with its own
bus handle — exactly as they would be separate boxes on a real harness.
三个发送节点、一个接收节点，各自一个线程、各自一个总线句柄 —— 和真车上各自
一个盒子一样。
"""

from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import can
import cantools

from . import e2e

DBC_PATH = Path(__file__).resolve().parent.parent / "dbc" / "lab_vehicle.dbc"


def load_db(path: Path = DBC_PATH):
    return cantools.database.load_file(str(path))


def data_id_of(msg) -> int:
    return int(msg.dbc.attributes["E2EDataId"].value)


@dataclass
class Faults:
    """Every field is a deliberate way to break the bus. All default to off."""
    stuck_counter: bool = False        # engine repeats the same counter forever
    bad_crc_every: int = 0             # engine corrupts every Nth CRC (0 = never)
    engine_stop_after: float = 0.0     # engine goes silent after N seconds (0 = never)
    jitter_ms: float = 0.0             # engine cycle time +/- this much, uniform
    drop_abs: float = 0.0              # ABS drops this fraction of its frames
    wrong_dlc: bool = False            # BCM sends BODY_STATUS with 6 bytes instead of 8


def drive_cycle(t: float) -> tuple[float, float, bool]:
    """(vehicle speed km/h, throttle %, brake) as a function of time.
    Accelerate for 8 s, cruise, brake to a stop, repeat every 24 s."""
    phase = t % 24.0
    if phase < 8.0:
        return 60.0 * phase / 8.0, 45.0, False
    if phase < 16.0:
        return 60.0, 20.0, False
    if phase < 20.0:
        return 60.0 * (1 - (phase - 16.0) / 4.0), 0.0, True
    return 0.0, 0.0, False


class CyclicSender(threading.Thread):
    """Base class: encode -> E2E protect -> send, every `cycle_ms`."""

    message_name = ""
    log_prefix = ""

    def __init__(self, bus: can.BusABC, db, faults: Faults, t0: float, stop: threading.Event):
        super().__init__(daemon=True, name=self.__class__.__name__)
        self.bus = bus
        self.db = db
        self.faults = faults
        self.t0 = t0
        self.stop_event = stop
        self.msg = db.get_message_by_name(self.message_name)
        self.data_id = data_id_of(self.msg)
        self.counter = 0
        self.sent = 0

    def signals(self, t: float) -> dict:  # override
        raise NotImplementedError

    def cycle_ms(self, t: float) -> float:
        return float(self.msg.cycle_time)

    def build(self, t: float) -> bytearray | None:
        sig = self.signals(t)
        sig[f"{self.message_name}_Counter"] = 0
        sig[f"{self.message_name}_CRC"] = 0
        payload = bytearray(self.msg.encode(sig))
        e2e.protect(payload, self.data_id, self.counter)
        self.counter = e2e.next_counter(self.counter)
        return payload

    def run(self):
        next_tx = time.monotonic()
        while not self.stop_event.is_set():
            t = time.monotonic() - self.t0
            payload = self.build(t)
            if payload is not None:
                self.bus.send(can.Message(arbitration_id=self.msg.frame_id,
                                          is_extended_id=False, data=payload))
                self.sent += 1
            next_tx += self.cycle_ms(t) / 1000.0
            delay = next_tx - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_tx = time.monotonic()  # we overran; do not try to catch up


class EngineEcu(CyclicSender):
    message_name = "ENGINE_DATA"

    def signals(self, t):
        speed, throttle, _ = drive_cycle(t)
        rpm = 800 + speed * 45 + throttle * 8 + 30 * math.sin(t * 7)
        return {
            "EngineSpeed": min(rpm, 8000),
            "ThrottlePos": throttle,
            "CoolantTemp": min(90, 20 + t * 2),
            "EngineRunning": 1,
        }

    def cycle_ms(self, t):
        base = super().cycle_ms(t)
        if self.faults.jitter_ms:
            return max(1.0, base + random.uniform(-self.faults.jitter_ms, self.faults.jitter_ms))
        return base

    def build(self, t):
        if self.faults.engine_stop_after and t > self.faults.engine_stop_after:
            return None
        payload = super().build(t)
        if self.faults.stuck_counter:
            self.counter = 3
            payload[e2e.COUNTER_BYTE] = (payload[e2e.COUNTER_BYTE] & 0xF0) | 3
            payload[e2e.CRC_BYTE] = e2e.crc8_j1850(bytes([self.data_id]) + bytes(payload[:7]))
        if self.faults.bad_crc_every and self.sent % self.faults.bad_crc_every == self.faults.bad_crc_every - 1:
            payload[e2e.CRC_BYTE] ^= 0xFF
        return payload


class AbsEcu(CyclicSender):
    message_name = "ABS_DATA"

    def signals(self, t):
        speed, _, brake = drive_cycle(t)
        return {
            "VehicleSpeed": speed,
            "WheelSpeedFL": speed * 1.01,
            "WheelSpeedFR": speed * 0.99,
            "BrakeActive": int(brake),
        }

    def build(self, t):
        if self.faults.drop_abs and random.random() < self.faults.drop_abs:
            self.counter = e2e.next_counter(self.counter)  # the frame existed, it just never arrived
            return None
        return super().build(t)


class BcmEcu(CyclicSender):
    message_name = "BODY_STATUS"

    def signals(self, t):
        return {
            "DoorFL": 0, "DoorFR": 0, "DoorRL": 0, "DoorRR": 0,
            "TurnIndicator": 1 if 16.0 < (t % 24.0) < 20.0 else 0,
            "LowBeam": 1,
            "OutsideTemp": 18.5,
        }

    def build(self, t):
        payload = super().build(t)
        if self.faults.wrong_dlc:
            return payload[:6]
        return payload


@dataclass
class ClusterState:
    engine_rpm: float = 0.0
    speed_kmh: float = 0.0
    turn: str = "Off"
    frames: int = 0
    unknown_ids: set = field(default_factory=set)
    e2e_events: list = field(default_factory=list)   # (t, message, verdict)
    timeouts: list = field(default_factory=list)     # (t, message)


class ClusterEcu(can.Listener):
    """The receiver. Decodes with the DBC, checks E2E, would drive the gauges.

    Runs as a python-can Listener rather than a thread: receive side is
    event-driven, and a real cluster is interrupt-driven too.
    """

    def __init__(self, db, t0: float, print_every: float = 0.5, out=print):
        self.db = db
        self.t0 = t0
        self.print_every = print_every
        self.out = out
        self.state = ClusterState()
        self.receivers = {m.frame_id: e2e.E2EReceiver(data_id_of(m))
                          for m in db.messages if "E2EDataId" in m.dbc.attributes}
        self.last_seen: dict[int, float] = {}
        self._next_print = t0 + print_every

    def on_message_received(self, msg: can.Message):
        t = time.monotonic() - self.t0
        self.state.frames += 1
        try:
            dbc_msg = self.db.get_message_by_frame_id(msg.arbitration_id)
        except KeyError:
            self.state.unknown_ids.add(msg.arbitration_id)
            return
        self.last_seen[msg.arbitration_id] = t
        if len(msg.data) != dbc_msg.length:
            self.state.e2e_events.append((t, dbc_msg.name, f"dlc {len(msg.data)} != {dbc_msg.length}"))
            return
        rx = self.receivers.get(msg.arbitration_id)
        if rx is not None:
            verdict = rx.check(bytes(msg.data))
            if verdict not in ("ok", "initial"):
                self.state.e2e_events.append((t, dbc_msg.name, verdict))
                return  # a frame that failed E2E must not reach the gauges
        decoded = self.db.decode_message(msg.arbitration_id, msg.data)
        if dbc_msg.name == "ENGINE_DATA":
            self.state.engine_rpm = decoded["EngineSpeed"]
        elif dbc_msg.name == "ABS_DATA":
            self.state.speed_kmh = decoded["VehicleSpeed"]
        elif dbc_msg.name == "BODY_STATUS":
            self.state.turn = str(decoded["TurnIndicator"])
        self._maybe_print(t)

    def check_timeouts(self, t: float):
        """Called from the main loop, not from on_message_received — a message
        that stopped arriving will never trigger a receive callback.
        从主循环调用，而不是收包回调: 不再到达的报文永远不会触发回调。"""
        # TODO(you) — project 01, day 4
        # For every cyclic message in self.receivers: if it has been seen and
        # t - last_seen > 3 * cycle_time, append (t, name) to state.timeouts
        # once (not every call), and clear the gauge value it feeds. Then decide:
        # should the cluster show the *last* speed or *zero* when ABS_DATA
        # times out? Write your answer in the README; there is a right one.
        # 超时后仪表该显示"最后一次车速"还是"零"? 把答案写进 README，这题有正解。
        pass

    def _maybe_print(self, t: float):
        now = time.monotonic()
        if now < self._next_print:
            return
        self._next_print = now + self.print_every
        s = self.state
        self.out(f"cluster  t={t:6.2f}s  rpm={s.engine_rpm:6.0f}  speed={s.speed_kmh:5.1f} km/h  "
                 f"turn={s.turn:<6}  frames={s.frames}  e2e_faults={len(s.e2e_events)}")
