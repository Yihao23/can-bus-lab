"""Integration on python-can's in-process virtual bus. No vcan, no sudo."""
import threading
import time
import unittest

import can

from vehicle import e2e
from vehicle.ecus import AbsEcu, BcmEcu, ClusterEcu, EngineEcu, Faults, load_db


def run_vehicle(faults: Faults, seconds: float = 0.6):
    db = load_db()
    stop = threading.Event()
    t0 = time.monotonic()
    buses = [can.Bus(interface="virtual", channel="test") for _ in range(4)]
    senders = [EngineEcu(buses[0], db, faults, t0, stop),
               AbsEcu(buses[1], db, faults, t0, stop),
               BcmEcu(buses[2], db, faults, t0, stop)]
    cluster = ClusterEcu(db, t0, out=lambda *_: None)
    notifier = can.Notifier(buses[3], [cluster])
    for s in senders:
        s.start()
    # Drive check_timeouts from here the way __main__'s main loop does — a
    # timeout can never be detected inside a receive callback, so something
    # outside the callback has to poll for it.
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        time.sleep(0.02)
        cluster.check_timeouts(time.monotonic() - t0)
    stop.set()
    for s in senders:
        s.join(1)
    notifier.stop()
    for b in buses:
        b.shutdown()
    return senders, cluster


class VehicleTest(unittest.TestCase):
    def test_healthy_bus_decodes_and_passes_e2e(self):
        senders, cluster = run_vehicle(Faults())
        self.assertGreater(cluster.state.frames, 30)
        self.assertEqual(cluster.state.e2e_events, [])
        self.assertGreater(cluster.state.engine_rpm, 700)
        self.assertEqual(cluster.state.unknown_ids, set())

    def test_bad_crc_is_caught_and_kept_off_the_gauges(self):
        # bad_crc_every=3, not 2, on purpose. A CRC-rejected frame is dropped
        # before its counter is read, so it does not advance last_counter; the
        # next good frame then looks like it skipped a count. With every 2nd
        # frame bad, *every* good frame would land on that gap and be judged
        # "lost", never "ok". With every 3rd frame bad, two good frames still
        # arrive back to back, so the receiver sees a clean +1 and reports "ok".
        # (Distinguishing a corrupted frame from a truly lost one — so counter=2
        # after a CRC drop reads as "ok" — is the pending_crc idea noted in the
        # README, left as an exercise.)
        _, cluster = run_vehicle(Faults(bad_crc_every=3))
        verdicts = {v for _, name, v in cluster.state.e2e_events if name == "ENGINE_DATA"}
        self.assertIn("crc", verdicts)
        rx = cluster.receivers[0x100]
        self.assertGreater(rx.stats["crc"], 0)
        self.assertGreater(rx.stats["ok"], 0)

    def test_wrong_dlc_is_rejected(self):
        _, cluster = run_vehicle(Faults(wrong_dlc=True))
        self.assertTrue(any(name == "BODY_STATUS" and v.startswith("dlc") for _, name, v in cluster.state.e2e_events))
        self.assertEqual(cluster.state.turn, "Off")   # never decoded a BODY_STATUS

    def test_stopped_message_times_out_exactly_once(self):
        # Engine goes silent at 0.2 s. Its cycle is 20 ms, so 3x = 60 ms later
        # the cluster should notice — once, not on every poll thereafter.
        _, cluster = run_vehicle(Faults(engine_stop_after=0.2), seconds=0.8)
        engine = [(t, name) for t, name in cluster.state.timeouts if name == "ENGINE_DATA"]
        self.assertEqual(len(engine), 1, "a single stop must produce a single timeout")
        self.assertGreater(engine[0][0], 0.2)   # reported after the stop, not before
        # ABS and BCM kept sending, so they must not be reported as timed out
        others = {name for _, name in cluster.state.timeouts}
        self.assertEqual(others, {"ENGINE_DATA"})

    def test_healthy_bus_never_times_out(self):
        _, cluster = run_vehicle(Faults(), seconds=0.6)
        self.assertEqual(cluster.state.timeouts, [])


if __name__ == "__main__":
    unittest.main()
