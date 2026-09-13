import unittest

from cananalyzer import dbc_lite, rules
from cananalyzer.parsers import candump

DBC = dbc_lite.load("""BO_ 256 ENGINE_DATA: 8 ENGINE
BO_ 416 ABS_DATA: 8 ABS
BA_ "GenMsgCycleTime" BO_ 256 20;
BA_ "E2EDataId" BO_ 256 17;
BA_ "GenMsgCycleTime" BO_ 416 20;
""")


def crc(data_id, payload7):
    return rules.crc8_j1850(bytes([data_id]) + payload7)


def engine_frame(t, counter, payload6=b"\x00" * 6, corrupt=False):
    p = payload6 + bytes([counter])
    c = crc(17, p) ^ (0xFF if corrupt else 0)
    return f"({t:.6f}) vcan0 100#{(p + bytes([c])).hex()}"


def log(lines):
    return candump.parse("\n".join(lines) + "\n")


def run(frames, dbc=DBC, **kw):
    ctx = rules.Context(frames=frames, dbc=dbc, **kw)
    return ctx, rules.run_all(ctx, fold=False)


def by_rule(findings, rule):
    return [f for f in findings if f.rule == rule]


class E2ERulesTest(unittest.TestCase):
    def test_crc_check_value(self):
        self.assertEqual(rules.crc8_j1850(b"123456789"), 0x4B)

    def test_healthy_sequence_has_no_findings(self):
        lines = [engine_frame(i * 0.020, i % 15) for i in range(40)]
        _, findings = run(log(lines))
        self.assertEqual(findings, [])

    def test_repeated_counter(self):
        lines = [engine_frame(i * 0.020, 3) for i in range(5)]
        _, findings = run(log(lines))
        r3 = by_rule(findings, "R003")
        self.assertEqual(len(r3), 4)
        self.assertEqual(r3[0].severity, "ERROR")
        self.assertIn("repeated", r3[0].message)

    def test_lost_frame_is_warning_big_jump_is_error(self):
        _, f = run(log([engine_frame(0, 1), engine_frame(0.02, 3)]))
        self.assertEqual(by_rule(f, "R003")[0].severity, "WARNING")
        _, f = run(log([engine_frame(0, 1), engine_frame(0.02, 9)]))
        self.assertEqual(by_rule(f, "R003")[0].severity, "ERROR")

    def test_wraparound_is_fine(self):
        _, f = run(log([engine_frame(0, 14), engine_frame(0.02, 0)]))
        self.assertEqual(by_rule(f, "R003"), [])

    def test_crc_mismatch(self):
        _, f = run(log([engine_frame(0, 0), engine_frame(0.02, 1, corrupt=True)]))
        r4 = by_rule(f, "R004")
        self.assertEqual(len(r4), 1)
        self.assertEqual(r4[0].frame_index, 1)


class TimingRulesTest(unittest.TestCase):
    def test_gap_from_dbc_cycle(self):
        lines = [engine_frame(t, i % 15) for i, t in enumerate([0, 0.02, 0.04, 0.10, 0.12])]
        _, f = run(log(lines))
        r1 = by_rule(f, "R001")
        self.assertEqual(len(r1), 1)
        self.assertIn("~2 frame(s) missing", r1[0].message)

    def test_learned_cycle_without_dbc(self):
        lines = [f"({i*0.1:.3f}) vcan0 555#00" for i in range(12)] + ["(1.900) vcan0 555#00"]
        ctx, f = run(log(lines), dbc={})
        self.assertEqual(ctx.cycle_source[0x555], "learned")
        self.assertAlmostEqual(ctx.cycle_ms[0x555], 100, places=3)
        self.assertEqual(len(by_rule(f, "R001")), 1)

    def test_event_messages_are_not_called_cyclic(self):
        gaps = [0, 0.01, 0.5, 0.51, 2.0, 2.01, 2.02, 5.0, 5.5, 5.51, 9.0, 9.01]
        lines = [f"({t:.3f}) vcan0 666#00" for t in gaps]
        ctx, f = run(log(lines), dbc={})
        self.assertNotIn(0x666, ctx.cycle_ms)
        self.assertEqual(by_rule(f, "R001"), [])

    def test_message_stopped(self):
        lines = [engine_frame(i * 0.020, i % 15) for i in range(10)]
        lines += [f"({t:.3f}) vcan0 1A0#0000000000000000" for t in [i * 0.02 for i in range(60)]]
        _, f = run(log(lines))
        r2 = by_rule(f, "R002")
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].subject, "ENGINE_DATA")

    def test_busload(self):
        # 8-byte std frames, worst case 135 bits; at 10 kbit/s, 100 frames/s is 135 %
        lines = [f"({i*0.01:.3f}) vcan0 100#{'00'*8}" for i in range(200)]
        ctx, f = run(log(lines), dbc={}, bitrate=10_000)
        self.assertTrue(by_rule(f, "R007"))
        self.assertGreater(rules.busload_windows(ctx)[0][1], 1.0)


class StructureRulesTest(unittest.TestCase):
    def test_dlc_and_unknown_id(self):
        lines = ["(0.000) vcan0 100#00000000", "(0.020) vcan0 999#00"]
        _, f = run(log(lines))
        self.assertEqual(by_rule(f, "R005")[0].subject, "ENGINE_DATA")
        r6 = by_rule(f, "R006")
        self.assertEqual((r6[0].subject, r6[0].severity), ("0x999", "INFO"))

    def test_no_dbc_means_no_unknown_ids(self):
        _, f = run(log(["(0.000) vcan0 999#00"]), dbc={})
        self.assertEqual(by_rule(f, "R006"), [])


class UdsRulesTest(unittest.TestCase):
    def test_nrc_and_pending_severities(self):
        lines = ["(0.000) x 7E0#0322F1A0AAAAAAAA", "(0.001) x 7E8#037F2233AAAAAAAA",
                 "(1.000) x 7E0#03220200AAAAAAAA", "(1.001) x 7E8#037F2278AAAAAAAA", "(1.300) x 7E8#05620200DEADAAAA"]
        _, f = run(log(lines), dbc={})
        r8 = by_rule(f, "R008")
        self.assertEqual([x.severity for x in r8], ["WARNING", "INFO"])
        self.assertEqual(by_rule(f, "R009"), [])     # 300 ms is fine after a 0x78

    def test_unanswered_and_late(self):
        lines = ["(0.000) x 7E0#023E00AAAAAAAAAA",                                       # never answered
                 "(1.000) x 7E0#0322F190AAAAAAAA", "(1.080) x 7E8#0762F19041424344"]     # 80 ms > P2 50 ms
        _, f = run(log(lines), dbc={})
        r9 = by_rule(f, "R009")
        self.assertEqual([x.severity for x in r9], ["ERROR", "WARNING"])

    def test_suppressed_tester_present_is_not_unanswered(self):
        _, f = run(log(["(0.000) x 7E0#023E80AAAAAAAAAA"]), dbc={})
        self.assertEqual(by_rule(f, "R009"), [])

    def test_isotp_error(self):
        lines = ["(0.000) x 7E8#101462F190574341", "(0.001) x 7E8#2330303030303031"]
        _, f = run(log(lines), dbc={})
        self.assertEqual(by_rule(f, "R010")[0].severity, "ERROR")


class CoalesceTest(unittest.TestCase):
    def test_folds_beyond_three(self):
        lines = [engine_frame(i * 0.020, 3) for i in range(30)]
        ctx = rules.Context(frames=log(lines), dbc=DBC)
        f = rules.run_all(ctx)
        r3 = by_rule(f, "R003")
        self.assertEqual(len(r3), 4)
        self.assertIn("26 more", r3[-1].message)


if __name__ == "__main__":
    unittest.main()
