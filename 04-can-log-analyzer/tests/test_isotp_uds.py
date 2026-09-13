import unittest

from cananalyzer import isotp, uds
from cananalyzer.parsers import candump

# Taken verbatim from samples/uds_session.log: a VIN read, one SF request,
# a three-frame response with one flow control in between.
VIN_READ = """(1.000000) uds 7E0#0322F190AAAAAAAA
(1.000600) uds 7E8#101462F190574341
(1.000800) uds 7E0#300800AAAAAAAAAA
(1.001200) uds 7E8#214E4C4142303030
(1.001250) uds 7E8#2230303030303031
"""

PENDING = """(2.000000) uds 7E0#03220200AAAAAAAA
(2.000500) uds 7E8#037F2278AAAAAAAA
(2.300900) uds 7E8#05620200DEADAAAA
"""


def frames(text):
    return candump.parse(text)


class IsoTpTest(unittest.TestCase):
    def test_multi_frame_reassembly(self):
        r = isotp.reassemble(frames(VIN_READ), {0x7E0, 0x7E8})
        self.assertEqual(len(r.messages), 2)
        req, resp = r.messages
        self.assertEqual(req.payload, bytes.fromhex("22F190"))
        self.assertEqual(resp.payload, bytes.fromhex("62F190") + b"WCANLAB0000000001")
        self.assertTrue(resp.complete)
        self.assertEqual(resp.frames, [1, 3, 4])
        self.assertEqual(len(r.flow_controls), 1)
        self.assertEqual((r.flow_controls[0].block_size, r.flow_controls[0].st_min), (8, 0))

    def test_sequence_error(self):
        bad = VIN_READ.replace("7E8#2230", "7E8#2330")   # SN 3 where 2 was expected
        r = isotp.reassemble(frames(bad), {0x7E0, 0x7E8})
        resp = [m for m in r.messages if m.can_id == 0x7E8][0]
        self.assertFalse(resp.complete)
        self.assertIn("sequence error", resp.error)

    def test_truncated_at_end_of_log(self):
        r = isotp.reassemble(frames(VIN_READ)[:2], {0x7E0, 0x7E8})
        resp = [m for m in r.messages if m.can_id == 0x7E8][0]
        self.assertFalse(resp.complete)
        self.assertIn("log ended", resp.error)

    def test_consecutive_frame_without_first(self):
        r = isotp.reassemble(frames(VIN_READ)[3:], {0x7E0, 0x7E8})
        self.assertTrue(all(not m.complete for m in r.messages))

    def test_single_frame_length_must_fit(self):
        r = isotp.reassemble(frames("(1.0) x 7E0#0922F190AAAAAAAA\n"), {0x7E0})
        self.assertFalse(r.messages[0].complete)


class UdsTest(unittest.TestCase):
    def test_pairing_and_latency(self):
        r = isotp.reassemble(frames(VIN_READ), {0x7E0, 0x7E8})
        txs, orphans = uds.pair(r.messages)
        self.assertEqual(len(txs), 1)
        self.assertEqual(orphans, [])
        tx = txs[0]
        self.assertEqual(tx.request.service, "ReadDataByIdentifier")
        self.assertFalse(tx.final.negative)
        self.assertAlmostEqual(tx.latency_ms, 1.25, places=2)

    def test_response_pending_is_not_final(self):
        r = isotp.reassemble(frames(PENDING), {0x7E0, 0x7E8})
        txs, _ = uds.pair(r.messages)
        tx = txs[0]
        self.assertEqual(tx.pending_count, 1)
        self.assertEqual(tx.final.src.payload[:2], bytes.fromhex("6202"))
        self.assertGreater(tx.latency_ms, 300)

    def test_negative_response_decoding(self):
        r = isotp.reassemble(frames("(1.0) x 7E0#022701AAAAAAAAAA\n(1.001) x 7E8#037F277FAAAAAAAA\n"), {0x7E0, 0x7E8})
        txs, _ = uds.pair(r.messages)
        self.assertEqual(txs[0].final.describe(), "NRC 0x7F serviceNotSupportedInActiveSession")
        self.assertEqual(txs[0].request.subfunction, 0x01)

    def test_suppress_positive_response_bit(self):
        r = isotp.reassemble(frames("(1.0) x 7E0#023E80AAAAAAAAAA\n"), {0x7E0})
        txs, _ = uds.pair(r.messages)
        self.assertTrue(txs[0].request.suppress_positive)
        self.assertIsNone(txs[0].final)

    def test_orphan_response(self):
        r = isotp.reassemble(frames("(1.0) x 7E8#027E00AAAAAAAAAA\n"), {0x7E8})
        txs, orphans = uds.pair(r.messages)
        self.assertEqual(txs, [])
        self.assertEqual(len(orphans), 1)


if __name__ == "__main__":
    unittest.main()
