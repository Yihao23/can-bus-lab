"""Pure-logic tests: no bus, no ISO-TP, microseconds each."""
import struct
import unittest

from ecu import uds_server as u


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.s = u.UdsServer()

    def test_default_to_extended_carries_timing(self):
        (r,) = self.s.handle(bytes([0x10, 0x03]))
        self.assertEqual(r[:2], bytes([0x50, 0x03]))
        p2, p2star = struct.unpack(">HH", r[2:])
        self.assertEqual((p2, p2star * 10), (u.P2_SERVER_MAX_MS, u.P2_STAR_SERVER_MAX_MS))

    def test_programming_needs_extended_first(self):
        self.assertEqual(self.s.handle(bytes([0x10, 0x02])), [u.negative(0x10, u.NRC_CONDITIONS_NOT_CORRECT)])
        self.s.handle(bytes([0x10, 0x03]))
        self.assertEqual(self.s.handle(bytes([0x10, 0x02]))[0][:2], bytes([0x50, 0x02]))

    def test_suppress_positive_response_bit(self):
        self.assertEqual(self.s.handle(bytes([0x10, 0x83])), [])
        self.assertEqual(self.s.state.session, u.SESSION_EXTENDED)

    def test_unknown_session_and_bad_length(self):
        self.assertEqual(self.s.handle(bytes([0x10, 0x07]))[0][2], u.NRC_SUBFUNCTION_NOT_SUPPORTED)
        self.assertEqual(self.s.handle(bytes([0x10]))[0][2], u.NRC_INCORRECT_LENGTH)

    def test_s3_timeout_drops_to_default_and_locks(self):
        self.s.handle(bytes([0x10, 0x03]), now=0.0)
        self._unlock(now=1.0)
        self.assertTrue(self.s.state.security_unlocked)
        self.s.tick(now=1.0 + u.S3_SERVER_MS / 1000 - 0.1)
        self.assertEqual(self.s.state.session, u.SESSION_EXTENDED)
        self.s.tick(now=1.0 + u.S3_SERVER_MS / 1000 + 0.1)
        self.assertEqual(self.s.state.session, u.SESSION_DEFAULT)
        self.assertFalse(self.s.state.security_unlocked)

    def test_tester_present_keeps_session_alive(self):
        self.s.handle(bytes([0x10, 0x03]), now=0.0)
        for t in (2.0, 4.0, 6.0, 8.0):
            self.assertEqual(self.s.handle(bytes([0x3E, 0x80]), now=t), [])   # suppressed
        self.assertEqual(self.s.state.session, u.SESSION_EXTENDED)
        self.assertEqual(self.s.handle(bytes([0x3E, 0x00]), now=9.0), [bytes([0x7E, 0x00])])

    def _unlock(self, now=0.0):
        (seed_rsp,) = self.s.handle(bytes([0x27, 0x01]), now=now)
        seed = seed_rsp[2:]
        return self.s.handle(bytes([0x27, 0x02]) + u.compute_key(seed), now=now)


class SecurityTest(SessionTest):
    def test_refused_in_default_session(self):
        self.assertEqual(self.s.handle(bytes([0x27, 0x01]))[0][2], u.NRC_SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION)

    def test_seed_key_happy_path(self):
        self.s.handle(bytes([0x10, 0x03]))
        self.assertEqual(self._unlock(), [bytes([0x67, 0x02])])
        self.assertTrue(self.s.state.security_unlocked)
        # already unlocked: seed of zeros, per ISO 14229
        self.assertEqual(self.s.handle(bytes([0x27, 0x01])), [bytes([0x67, 0x01, 0, 0, 0, 0])])

    def test_wrong_key_invalidates_seed(self):
        self.s.handle(bytes([0x10, 0x03]))
        self.s.handle(bytes([0x27, 0x01]))
        self.assertEqual(self.s.handle(bytes([0x27, 0x02, 1, 2, 3, 4]))[0][2], u.NRC_INVALID_KEY)
        self.assertEqual(self.s.state.failed_key_attempts, 1)
        # a second key without a fresh seed is a sequence error, not a second guess
        self.assertEqual(self.s.handle(bytes([0x27, 0x02, 1, 2, 3, 4]))[0][2], u.NRC_REQUEST_SEQUENCE_ERROR)

    def test_key_before_seed(self):
        self.s.handle(bytes([0x10, 0x03]))
        self.assertEqual(self.s.handle(bytes([0x27, 0x02, 0, 0, 0, 0]))[0][2], u.NRC_REQUEST_SEQUENCE_ERROR)

    def test_session_change_relocks(self):
        self.s.handle(bytes([0x10, 0x03]))
        self._unlock()
        self.s.handle(bytes([0x10, 0x03]))
        self.assertFalse(self.s.state.security_unlocked)

    # TODO(you) — project 02, day 6. Uncomment, fail, implement in _security_access.
    #
    # def test_three_wrong_keys_then_0x36_then_delay_0x37(self):
    #     self.s.handle(bytes([0x10, 0x03]), now=0.0)
    #     for i in range(3):
    #         self.s.handle(bytes([0x27, 0x01]), now=float(i))
    #         self.assertEqual(self.s.handle(bytes([0x27, 0x02, 9, 9, 9, 9]), now=float(i))[0][2], u.NRC_INVALID_KEY)
    #     self.assertEqual(self.s.handle(bytes([0x27, 0x01]), now=3.0)[0][2], u.NRC_EXCEEDED_NUMBER_OF_ATTEMPTS)
    #     self.assertEqual(self.s.handle(bytes([0x27, 0x01]), now=8.0)[0][2], u.NRC_REQUIRED_TIME_DELAY_NOT_EXPIRED)
    #     self.assertEqual(self.s.handle(bytes([0x27, 0x01]), now=14.0)[0][1], 0x27)   # positive again


class ReadDidTest(SessionTest):
    def test_vin_in_default_session(self):
        (r,) = self.s.handle(bytes([0x22, 0xF1, 0x90]))
        self.assertEqual(r[:3], bytes([0x62, 0xF1, 0x90]))
        self.assertEqual(len(r[3:]), 17)

    def test_live_did_uses_dbc_scaling(self):
        self.s.state.engine_speed_rpm = 1000.0
        (r,) = self.s.handle(bytes([0x22, 0x01, 0x00]))
        self.assertEqual(struct.unpack(">H", r[3:])[0] * 0.25, 1000.0)

    def test_multiple_dids_skip_unknown_ones(self):
        (r,) = self.s.handle(bytes([0x22, 0xF1, 0x95, 0xDE, 0xAD, 0x01, 0x01]))
        self.assertIn(bytes([0xF1, 0x95]), r)
        self.assertIn(bytes([0x01, 0x01]), r)
        self.assertNotIn(bytes([0xDE, 0xAD]), r)

    def test_all_unknown_is_out_of_range(self):
        self.assertEqual(self.s.handle(bytes([0x22, 0xDE, 0xAD]))[0][2], u.NRC_REQUEST_OUT_OF_RANGE)

    def test_odd_length(self):
        self.assertEqual(self.s.handle(bytes([0x22, 0xF1]))[0][2], u.NRC_INCORRECT_LENGTH)

    def test_secured_did(self):
        self.assertEqual(self.s.handle(bytes([0x22, 0xF1, 0xA0]))[0][2], u.NRC_SECURITY_ACCESS_DENIED)
        self.s.handle(bytes([0x10, 0x03]))
        self._unlock()
        self.assertEqual(self.s.handle(bytes([0x22, 0xF1, 0xA0]))[0][:3], bytes([0x62, 0xF1, 0xA0]))

    def test_slow_did_sends_pending_first(self):
        rs = self.s.handle(bytes([0x22, 0x02, 0x00]))
        self.assertEqual(len(rs), 2)
        self.assertEqual(rs[0], bytes([0x7F, 0x22, 0x78]))
        self.assertEqual(rs[1][0], 0x62)


class DtcTest(SessionTest):
    def test_count_by_status_mask(self):
        (r,) = self.s.handle(bytes([0x19, 0x01, 0x08]))    # confirmed
        self.assertEqual(struct.unpack(">H", r[4:])[0], 2)
        (r,) = self.s.handle(bytes([0x19, 0x01, 0x04]))    # pending
        self.assertEqual(struct.unpack(">H", r[4:])[0], 1)

    def test_list_by_status_mask(self):
        (r,) = self.s.handle(bytes([0x19, 0x02, 0xFF]))
        records = r[3:]
        self.assertEqual(len(records) % 4, 0)
        self.assertEqual(len(records) // 4, 3)
        self.assertEqual(records[:3], (0x011F00).to_bytes(3, "big"))

    def test_unsupported_subfunction(self):
        self.assertEqual(self.s.handle(bytes([0x19, 0x0A, 0xFF]))[0][2], u.NRC_SUBFUNCTION_NOT_SUPPORTED)

    # TODO(you) — project 02, day 6: 0x14 ClearDiagnosticInformation.
    # Request is 0x14 + 3-byte group (0xFFFFFF = all). Must refuse in default
    # session (0x7F) and refuse a group that does not exist (0x31). After
    # clearing, 0x19 0x01 0xFF must report 0. Write these tests first.


class ResetAndUnsupportedTest(SessionTest):
    def test_reset_rules(self):
        self.assertEqual(self.s.handle(bytes([0x11, 0x01]))[0][2], u.NRC_SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION)
        self.s.handle(bytes([0x10, 0x03]))
        self.assertEqual(self.s.handle(bytes([0x11, 0x01]))[0][2], u.NRC_CONDITIONS_NOT_CORRECT)   # engine running
        self.s.state.engine_speed_rpm = 0
        self.assertEqual(self.s.handle(bytes([0x11, 0x01])), [bytes([0x51, 0x01])])
        self.assertEqual(self.s.state.session, u.SESSION_DEFAULT)
        self.assertEqual(self.s.state.resets, 1)

    def test_unknown_service(self):
        self.assertEqual(self.s.handle(bytes([0x99, 0x00])), [bytes([0x7F, 0x99, 0x11])])

    def test_write_did_not_yet_supported(self):
        # Goes away when you do the day-6 TODO. That is the point of it.
        self.assertEqual(self.s.handle(bytes([0x2E, 0xF1, 0x90]) + b"X" * 17)[0][2], u.NRC_SERVICE_NOT_SUPPORTED)


if __name__ == "__main__":
    unittest.main()
