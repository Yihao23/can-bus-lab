import unittest

from vehicle import e2e
from vehicle.ecus import data_id_of, load_db


class DbcTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = load_db()

    def test_every_e2e_message_matches_the_e2e_layout(self):
        # The DBC and e2e.py describe the same bytes. If someone moves the
        # counter signal in the DBC, this is the test that notices.
        for msg in self.db.messages:
            if "E2EDataId" not in msg.dbc.attributes:
                continue
            with self.subTest(msg.name):
                counter = msg.get_signal_by_name(f"{msg.name}_Counter")
                crc = msg.get_signal_by_name(f"{msg.name}_CRC")
                self.assertEqual(msg.length, 8)
                self.assertEqual(counter.length, 4)
                self.assertEqual(crc.length, 8)
                sig = {s.name: 0 for s in msg.signals}
                sig[f"{msg.name}_Counter"] = 0xA
                sig[f"{msg.name}_CRC"] = 0x5C
                raw = msg.encode(sig, strict=False)
                self.assertEqual(raw[e2e.COUNTER_BYTE] & 0x0F, 0xA, "counter must be low nibble of byte 6")
                self.assertEqual(raw[e2e.CRC_BYTE], 0x5C, "CRC must be byte 7")

    def test_cycle_times_and_data_ids(self):
        eng = self.db.get_message_by_name("ENGINE_DATA")
        body = self.db.get_message_by_name("BODY_STATUS")
        self.assertEqual(eng.cycle_time, 20)
        self.assertEqual(body.cycle_time, 100)
        self.assertNotEqual(data_id_of(eng), data_id_of(body))

    def test_motorola_signal_round_trip(self):
        # BODY_STATUS is big-endian on purpose. -12.5 degC at factor 0.5 is raw
        # -25 = 0xE7 in byte 1, and the start bit written in the DBC (15) is the
        # MSB of that byte — the Motorola convention.
        body = self.db.get_message_by_name("BODY_STATUS")
        sig = {s.name: 0 for s in body.signals}
        sig["OutsideTemp"] = -12.5
        sig["DoorFL"] = 1
        raw = body.encode(sig)
        self.assertEqual(raw[1], 0xE7)
        self.assertEqual(raw[0] & 0x80, 0x80, "DoorFL is bit 7 of byte 0")
        back = self.db.decode_message(body.frame_id, raw)
        self.assertEqual(back["OutsideTemp"], -12.5)

    def test_intel_signal_byte_order(self):
        eng = self.db.get_message_by_name("ENGINE_DATA")
        sig = {s.name: 0 for s in eng.signals}
        sig["EngineSpeed"] = 0x1234 * 0.25   # raw 0x1234
        raw = eng.encode(sig)
        self.assertEqual(raw[0], 0x34, "Intel: low byte first")
        self.assertEqual(raw[1], 0x12)


if __name__ == "__main__":
    unittest.main()
