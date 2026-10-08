import hashlib
import json
import unittest
from pathlib import Path

from scripts.compound_diagnosis import build_protocol as build_compound_protocol
from scripts.scaling_large import build_protocol as build_scaling_protocol
from watchdelta.active_diagnosis import BOUNDARIES, hypothesis_space

ROOT = Path(__file__).resolve().parents[1]


class V4ProtocolTests(unittest.TestCase):
    def test_frozen_compound_protocol_matches_generator(self):
        path = ROOT / "protocols/compound-diagnosis.json"
        raw = path.read_bytes()
        self.assertEqual(json.loads(raw), build_compound_protocol())
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            (ROOT / "protocols/compound-diagnosis.sha256").read_text().strip(),
        )
        protocol = json.loads(raw)
        self.assertEqual(len(protocol["units"]), 62)
        self.assertEqual(protocol["hypothesis_count"], len(hypothesis_space()))
        self.assertEqual(protocol["known_boundaries"], list(BOUNDARIES))
        self.assertEqual(protocol["fixed_panel_size"], 6)
        known = [unit for unit in protocol["units"] if unit["supported"]]
        unknown = [unit for unit in protocol["units"] if not unit["supported"]]
        expected = {hypothesis for hypothesis in hypothesis_space() if len(hypothesis) >= 2}
        self.assertEqual({frozenset(unit["truth"]) for unit in known}, expected)
        self.assertEqual(len(known), 50)
        self.assertEqual(len(unknown), 12)
        for truth in expected:
            self.assertEqual(sum(frozenset(unit["truth"]) == truth for unit in known), 2)

    def test_frozen_scaling_protocol_matches_generator(self):
        path = ROOT / "protocols/scaling-large.json"
        raw = path.read_bytes()
        self.assertEqual(json.loads(raw), build_scaling_protocol())
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            (ROOT / "protocols/scaling-large.sha256").read_text().strip(),
        )
        protocol = json.loads(raw)
        self.assertEqual(len(protocol["jobs"]), 32)
        self.assertEqual(protocol["sizes"], [1000, 5000])
        self.assertEqual({job["filesystem"] for job in protocol["jobs"]}, {"overlay", "tmpfs"})


if __name__ == "__main__":
    unittest.main()
