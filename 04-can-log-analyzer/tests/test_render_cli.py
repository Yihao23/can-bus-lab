import json
import os
import tempfile
import unittest
from pathlib import Path

from cananalyzer import cli

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


class CliTest(unittest.TestCase):
    def run_cli(self, *args):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(list(args))
        return code, out.getvalue()

    def test_faulty_sample_all_six_faults(self):
        code, out = self.run_cli(str(SAMPLES / "faulty.log"), "--dbc", str(SAMPLES / "lab_vehicle.dbc"), "--fail-on-error")
        self.assertEqual(code, 1)
        for rule in ("R001", "R002", "R003", "R004", "R005"):
            self.assertIn(rule, out)
        self.assertIn("alive counter repeated", out)
        self.assertIn("stopped", out)
        self.assertIn("DLC 6 but DBC says 8", out)

    def test_healthy_sample_is_clean(self):
        code, out = self.run_cli(str(SAMPLES / "healthy.log"), "--dbc", str(SAMPLES / "lab_vehicle.dbc"), "--fail-on-error")
        self.assertEqual(code, 0)
        self.assertIn("findings: 0", out)

    def test_uds_sample(self):
        code, out = self.run_cli(str(SAMPLES / "uds_session.log"))
        self.assertEqual(code, 0)
        self.assertIn("uds transactions: 15", out)
        self.assertIn("+1x0x78", out)

    def test_json_keeps_every_finding(self):
        code, out = self.run_cli(str(SAMPLES / "faulty.log"), "--dbc", str(SAMPLES / "lab_vehicle.dbc"), "--format", "json")
        doc = json.loads(out)
        self.assertGreater(len(doc["findings"]), 100)     # unfolded
        self.assertEqual({r["rule"] for r in doc["findings"]} >= {"R002", "R003", "R004", "R005"}, True)
        self.assertTrue(doc["busload"])

    def test_md_html_mermaid_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            cases = (("md", "```mermaid", "uds_session.log"), ("mermaid", "sequenceDiagram", "uds_session.log"),
                     ("html", "<svg", "faulty.log"), ("html", "<h2>UDS</h2>", "uds_session.log"))
            for fmt, needle, sample in cases:
                path = os.path.join(d, f"r-{sample}.{fmt}")
                code, _ = self.run_cli(str(SAMPLES / sample), "--format", fmt, "-o", path)
                self.assertEqual(code, 0)
                self.assertIn(needle, Path(path).read_text())

    def test_not_a_candump_log(self):
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
            f.write("hello\n")
        try:
            code, _ = self.run_cli(f.name)
            self.assertEqual(code, 2)
        finally:
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
