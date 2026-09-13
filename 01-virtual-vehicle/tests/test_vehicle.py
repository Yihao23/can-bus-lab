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
    time.sleep(seconds)
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
        _, cluster = run_vehicle(Faults(bad_crc_every=2))
        verdicts = {v for _, name, v in cluster.state.e2e_events if name == "ENGINE_DATA"}
        self.assertIn("crc", verdicts)
        rx = cluster.receivers[0x100]
        self.assertGreater(rx.stats["crc"], 0)
        self.assertGreater(rx.stats["ok"], 0)

    def test_wrong_dlc_is_rejected(self):
        _, cluster = run_vehicle(Faults(wrong_dlc=True))
        self.assertTrue(any(name == "BODY_STATUS" and v.startswith("dlc") for _, name, v in cluster.state.e2e_events))
        self.assertEqual(cluster.state.turn, "Off")   # never decoded a BODY_STATUS


if __name__ == "__main__":
    unittest.main()
