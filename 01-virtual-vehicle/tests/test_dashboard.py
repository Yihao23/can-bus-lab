"""The dashboard's data side. The page itself is checked by opening it."""
import json
import threading
import time
import unittest
import urllib.request

import can

from vehicle import dashboard
from vehicle.ecus import AbsEcu, BcmEcu, ClusterEcu, EngineEcu, Faults, load_db


class ListenerTest(unittest.TestCase):
    def test_tail_and_load(self):
        t0 = time.monotonic()
        lst = dashboard.DashboardListener(t0, bitrate=10_000)
        for i in range(30):
            lst.on_message_received(can.Message(arbitration_id=0x100, data=bytes(8), is_extended_id=False))
        self.assertEqual(len(lst.tail()), dashboard.RECENT_FRAMES)
        self.assertIn("100  [8]  00 00", lst.tail()[-1])
        # 30 x 135 bits in the last second at 10 kbit/s = 40.5 %
        self.assertAlmostEqual(lst.load(), 30 * 135 / 10_000, places=3)
        self.assertEqual(lst.total, 30)


class ServerTest(unittest.TestCase):
    def setUp(self):
        db = load_db()
        self.stop = threading.Event()
        t0 = time.monotonic()
        self.buses = [can.Bus(interface="virtual", channel="dash-test") for _ in range(4)]
        self.senders = [EngineEcu(self.buses[0], db, Faults(), t0, self.stop),
                        AbsEcu(self.buses[1], db, Faults(), t0, self.stop),
                        BcmEcu(self.buses[2], db, Faults(), t0, self.stop)]
        self.cluster = ClusterEcu(db, t0, out=lambda *_: None)
        self.listener = dashboard.DashboardListener(t0)
        self.notifier = can.Notifier(self.buses[3], [self.cluster, self.listener])
        self.server = dashboard.serve(lambda: dashboard.snapshot(self.cluster, self.listener, self.senders), port=0)
        for s in self.senders:
            s.start()
        time.sleep(0.4)

    def tearDown(self):
        self.stop.set()
        for s in self.senders:
            s.join(1)
        self.notifier.stop()
        self.server.shutdown()
        for b in self.buses:
            b.shutdown()

    def url(self, path):
        return f"http://127.0.0.1:{self.server.server_port}{path}"

    def test_state_endpoint(self):
        with urllib.request.urlopen(self.url("/state"), timeout=2) as r:
            d = json.load(r)
        self.assertGreater(d["rpm"], 700)
        self.assertEqual(len(d["messages"]), 3)
        self.assertEqual({m["name"] for m in d["messages"]}, {"ENGINE_DATA", "ABS_DATA", "BODY_STATUS"})
        self.assertTrue(all(m["age_ms"] is not None for m in d["messages"]))
        self.assertTrue(d["low_beam"])
        self.assertEqual(d["doors"], [False] * 4)
        self.assertEqual(d["outside_temp"], 18.5)          # Motorola signal, decoded by the cluster
        self.assertGreater(d["busload"], 0.005)   # the window is 1 s and setUp waited 0.4 s
        self.assertGreater(d["sent"]["ENGINE_DATA"], 5)
        self.assertTrue(d["frames"])

    def test_page_and_events(self):
        with urllib.request.urlopen(self.url("/"), timeout=2) as r:
            self.assertIn(b"EventSource('/events')", r.read())
        req = urllib.request.Request(self.url("/events"))
        with urllib.request.urlopen(req, timeout=2) as r:
            first = r.readline()
        self.assertTrue(first.startswith(b"data: {"))
        self.assertIn("rpm", json.loads(first[6:]))

    def test_404(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(self.url("/nope"), timeout=2)
        self.assertEqual(cm.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
