import unittest

from vehicle import e2e


class Crc8Test(unittest.TestCase):
    def test_check_value(self):
        # The published check value for CRC-8/SAE-J1850. If this fails, the
        # polynomial, init or xorout is wrong — not the caller.
        self.assertEqual(e2e.crc8_j1850(b"123456789"), 0x4B)

    def test_single_bit_flip_is_detected(self):
        payload = bytearray(b"\x10\x20\x30\x40\x50\x60\x70\x00")
        e2e.protect(payload, data_id=17, counter=5)
        self.assertTrue(e2e.crc_ok(payload, 17))
        payload[2] ^= 0x01
        self.assertFalse(e2e.crc_ok(payload, 17))

    def test_data_id_is_part_of_the_crc(self):
        # Same bytes, different DataID -> different CRC. This is what stops a
        # frame from message A being accepted as message B after an ID clash.
        a = e2e.protect(bytearray(8), data_id=17, counter=0)
        b = e2e.protect(bytearray(8), data_id=18, counter=0)
        self.assertNotEqual(a[e2e.CRC_BYTE], b[e2e.CRC_BYTE])
        self.assertFalse(e2e.crc_ok(a, 18))


class CounterTest(unittest.TestCase):
    def test_wraps_at_14_not_15(self):
        self.assertEqual(e2e.next_counter(13), 14)
        self.assertEqual(e2e.next_counter(14), 0)

    def test_protect_keeps_high_nibble(self):
        payload = bytearray(8)
        payload[e2e.COUNTER_BYTE] = 0xA0
        e2e.protect(payload, 1, 7)
        self.assertEqual(payload[e2e.COUNTER_BYTE], 0xA7)

    def test_rejects_reserved_counter(self):
        with self.assertRaises(ValueError):
            e2e.protect(bytearray(8), 1, 15)


class ReceiverTest(unittest.TestCase):
    def frames(self, counters, data_id=17):
        return [bytes(e2e.protect(bytearray(8), data_id, c)) for c in counters]

    def test_crc_failure_is_reported_before_counter(self):
        rx = e2e.E2EReceiver(17)
        bad = bytearray(self.frames([0])[0])
        bad[0] ^= 0x80
        self.assertEqual(rx.check(bytes(bad)), "crc")
        self.assertEqual(rx.stats["crc"], 1)

    # TODO(you) — project 01, day 3. Uncomment, watch them fail, then implement
    # E2EReceiver.check in vehicle/e2e.py.
    # 取消注释，看着它们失败，再去实现 E2EReceiver.check。
    #
    def test_first_frame_is_initial(self):
        rx = e2e.E2EReceiver(17)
        self.assertEqual(rx.check(self.frames([4])[0]), "initial")
    
    def test_consecutive_is_ok_including_wrap(self):
        rx = e2e.E2EReceiver(17)
        verdicts = [rx.check(f) for f in self.frames([13, 14, 0, 1])]
        self.assertEqual(verdicts, ["initial", "ok", "ok", "ok"])
    
    def test_repeated_counter(self):
        rx = e2e.E2EReceiver(17)
        verdicts = [rx.check(f) for f in self.frames([5, 5])]
        self.assertEqual(verdicts[-1], "repeated")
    
    def test_small_gap_is_lost_large_gap_is_wrong_seq(self):
        rx = e2e.E2EReceiver(17)
        self.assertEqual([rx.check(f) for f in self.frames([2, 4])][-1], "lost")
        rx = e2e.E2EReceiver(17)
        self.assertEqual([rx.check(f) for f in self.frames([2, 9])][-1], "wrong_seq")
    
    def test_backwards_is_wrong_seq(self):
        rx = e2e.E2EReceiver(17)
        self.assertEqual([rx.check(f) for f in self.frames([6, 5])][-1], "wrong_seq")


if __name__ == "__main__":
    unittest.main()
