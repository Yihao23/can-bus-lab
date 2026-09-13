import unittest

from cananalyzer import dbc_lite
from cananalyzer.parsers import candump

SAMPLE = """(1789297083.621266) vcan0 100#2412703C01000033
(1789297083.621736) vcan0 1A0#0200000000000074 R
(1789297083.622000) vcan0 18FEF100#0102030405060708
(1789297083.623000) vcan0 7E0##10322F190AAAAAAAAAAAAAAAA
(1789297083.624000) vcan0 123#R
this line is noise
"""

DBC = """BO_ 256 ENGINE_DATA: 8 ENGINE
 SG_ EngineSpeed : 0|16@1+ (0.25,0) [0|16383.75] "rpm" CLUSTER
 SG_ CoolantTemp : 24|8@1+ (1,-40) [-40|215] "degC" CLUSTER
BO_ 768 BODY_STATUS: 8 BCM
 SG_ OutsideTemp : 15|8@0- (0.5,0) [-64|63.5] "degC" CLUSTER
BO_ 2566844672 CCVS: 8 ENGINE
 SG_ WheelSpeed : 8|16@1+ (0.00390625,0) [0|250.996] "km/h" CLUSTER
BA_ "GenMsgCycleTime" BO_ 256 20;
BA_ "E2EDataId" BO_ 256 17;
BA_ "GenMsgCycleTime" BO_ 2566844672 100;
"""


class CandumpParserTest(unittest.TestCase):
    def test_all_line_shapes(self):
        self.assertTrue(candump.sniff(SAMPLE))
        frames = candump.parse(SAMPLE)
        self.assertEqual(len(frames), 5)
        self.assertEqual(frames[0].can_id, 0x100)
        self.assertEqual(frames[0].data, bytes.fromhex("2412703C01000033"))
        self.assertFalse(frames[0].extended)
        self.assertEqual(frames[1].data[-1], 0x74)          # trailing direction flag ignored
        self.assertTrue(frames[2].extended)
        self.assertEqual(frames[2].can_id, 0x18FEF100)
        self.assertTrue(frames[3].fd)
        self.assertEqual(len(frames[3].data), 12)
        self.assertTrue(frames[4].remote)
        self.assertEqual([f.index for f in frames], [0, 1, 2, 3, 4])

    def test_sniff_rejects_other_formats(self):
        self.assertFalse(candump.sniff("[{\"MessageType\": 2}]\n"))
        self.assertFalse(candump.sniff("  can0  100   [8]  24 12 70 3C 01 00 00 33\n"))  # candump without -L


class DbcLiteTest(unittest.TestCase):
    def setUp(self):
        self.db = dbc_lite.load(DBC)

    def test_messages_and_attributes(self):
        self.assertEqual(self.db[0x100].name, "ENGINE_DATA")
        self.assertEqual(self.db[0x100].cycle_ms, 20)
        self.assertEqual(self.db[0x100].e2e_data_id, 17)
        self.assertIsNone(self.db[0x300].cycle_ms)

    def test_extended_id_flag_is_stripped(self):
        self.assertIn(0x18FEF100, self.db)
        self.assertEqual(self.db[0x18FEF100].cycle_ms, 100)

    def test_intel_decode(self):
        msg = self.db[0x100]
        dec = dbc_lite.decode_message(msg, bytes.fromhex("2412703C01000033"))
        self.assertEqual(dec["EngineSpeed"], 0x1224 * 0.25)
        self.assertEqual(dec["CoolantTemp"], 0x3C - 40)

    def test_too_short_frame_gives_no_value(self):
        msg = self.db[0x100]
        self.assertIsNone(dbc_lite.decode_signal(msg.signals[1], b"\x24\x12"))

    # TODO(you) — project 04, day 12. Uncomment, fail, implement Motorola in decode_signal.
    #
    # def test_motorola_signed_decode(self):
    #     msg = self.db[0x300]
    #     dec = dbc_lite.decode_message(msg, bytes.fromhex("00E7000000000000"))
    #     self.assertEqual(dec["OutsideTemp"], -12.5)
    #
    # def test_motorola_crossing_a_byte_boundary(self):
    #     sig = dbc_lite.Signal("x", start=3, length=12, little_endian=False, signed=False, factor=1, offset=0, unit="")
    #     # bits 3..0 of byte 0 are the top nibble, byte 1 is the low byte: 0x0A, 0xBC -> 0xABC
    #     self.assertEqual(dbc_lite.decode_signal(sig, bytes([0x0A, 0xBC])), 0xABC)


if __name__ == "__main__":
    unittest.main()
