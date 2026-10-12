"""Owned benign fixtures for the standalone integration analyzer's premises.

No server is started and no retained study record is edited. Other integration
validators are stubbed only to isolate the Uvicorn table path. The Uvicorn
loader, qualification function, and retained-byte checks run without mocks.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from watchdelta.core import source_fingerprint


MODULE_PATH = Path(os.environ.get(
    "WATCHDELTA_INTEGRATION_ANALYZER",
    str(Path(__file__).resolve().parents[1] / "scripts/analyze_integrations.py"),
))
SPEC = importlib.util.spec_from_file_location("integration_candidate", MODULE_PATH)
analysis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analysis)


class IntegrationQualificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="p121-integration-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.results = self.root / "results"
        self.dataset = self.results / "uvicorn-integration"
        self.case = self.dataset / "episodes/owned-benign"
        for tree in ("work", "clean"):
            (self.case / tree / "src").mkdir(parents=True)
            (self.case / tree / "src/index.md").write_bytes(b"final source\n")
        for tree in ("observed", "clean/out"):
            (self.case / tree).mkdir(parents=True, exist_ok=True)
            (self.case / tree / "index.html").write_bytes(b"new")
        digest = lambda data: hashlib.sha256(data).hexdigest()
        expected = {"index.html": digest(b"new")}
        self.record = {
            "id": "owned-benign", "tool": "docs", "mode": "include_md",
            "scenario": "same_size", "status": "matched", "ready_ns": 1,
            "edit": {"start_ns": 2, "end_ns": 3, "obligation": True},
            "snapshot_stable": True, "obligation_consistent": True,
            "initial_projection": {"index.html": digest(b"initial")},
            "observed_projection": expected, "served_projection": deepcopy(expected),
            "served_matches_disk": True, "rerenders": 1,
            "clean": {"returncode": 0, "projection": deepcopy(expected),
                      "source_sha256": source_fingerprint(self.case / "work", "docs")[0]},
        }
        raw = json.dumps({"jobs": [{"id": "owned-benign", "tool": "docs",
                                    "mode": "include_md", "scenario": "same_size"}]})
        (self.dataset / "protocol.json").write_text(raw, encoding="utf-8")
        (self.dataset / "protocol.sha256").write_text(digest(raw.encode()), encoding="utf-8")
        (self.dataset / "complete.json").write_text('{"episodes": 1}', encoding="utf-8")
        (self.results / "derived").mkdir()
        self.save()

    def save(self, *, summary_status="matched"):
        raw = json.dumps(self.record)
        (self.dataset / "records.jsonl").write_text(raw + "\n", encoding="utf-8")
        (self.case / "record.json").write_text(raw, encoding="utf-8")
        summary = {"datasets": {"uvicorn-integration": {
            "n": 1, "outcomes": {summary_status: 1},
        }}}
        (self.results / "derived/summary.json").write_text(json.dumps(summary), encoding="utf-8")

    def run_main(self, writes):
        with patch.object(analysis, "validate_hypercorn", return_value=([], {"id": "unused"})), \
             patch.object(analysis, "validate_vite", return_value=([], {"cases": 0, "changed": 0})), \
             patch.object(analysis, "validate_mkdocs", return_value=([], {
                 "episodes": 0, "burst_events": 0, "burst_builds": 0})), \
             patch.object(analysis, "write", side_effect=lambda path, body: writes.append((path, body))), \
             patch("sys.argv", ["analyze_integrations", "--results", str(self.results),
                                "--paper", str(self.root / "paper")]), \
             redirect_stdout(io.StringIO()):
            analysis.main()

    def assert_rejected_before_writes(self):
        writes = []
        with self.assertRaises(RuntimeError):
            self.run_main(writes)
        self.assertEqual(writes, [], "invalid input generated artifacts before rejection")
        self.assertFalse((self.root / "paper").exists())

    def test_valid_input_still_generates_success_table(self):
        writes = []
        self.run_main(writes)
        table = next(body for path, body in writes if path.name == "integrations.tex")
        self.assertIn("Uvicorn include md & Markdown same size & 1/1 & 1", table)

    def test_failed_reference_exit_is_rejected(self):
        self.record["clean"]["returncode"] = 7
        self.save()
        self.assert_rejected_before_writes()

    def test_missing_reference_exit_is_rejected(self):
        del self.record["clean"]["returncode"]
        self.save()
        self.assert_rejected_before_writes()

    def test_boolean_reference_exit_is_not_success(self):
        self.record["clean"]["returncode"] = False
        self.save()
        self.assert_rejected_before_writes()

    def test_false_snapshot_stability_is_rejected(self):
        self.record["snapshot_stable"] = False
        self.save()
        self.assert_rejected_before_writes()

    def test_missing_snapshot_stability_is_rejected(self):
        del self.record["snapshot_stable"]
        self.save()
        self.assert_rejected_before_writes()

    def test_served_disk_mismatch_cannot_retain_matched_status(self):
        self.record["served_projection"] = {"index.html": hashlib.sha256(b"old").hexdigest()}
        self.record["served_matches_disk"] = False
        self.save()
        self.assert_rejected_before_writes()

    def test_missing_http_comparison_is_rejected(self):
        del self.record["served_matches_disk"]
        self.save()
        self.assert_rejected_before_writes()

    def test_source_drift_is_rejected(self):
        (self.case / "work/src/index.md").write_bytes(b"drift\n")
        self.assert_rejected_before_writes()

    def test_retained_output_drift_is_rejected(self):
        (self.case / "observed/index.html").write_bytes(b"drift")
        self.assert_rejected_before_writes()

    def test_cached_summary_must_match_qualified_records(self):
        self.save(summary_status="stale")
        self.assert_rejected_before_writes()

    def test_valid_nonconform_is_not_counted_as_success(self):
        self.record["served_projection"] = {"index.html": hashlib.sha256(b"old").hexdigest()}
        self.record["served_matches_disk"] = False
        self.record["status"] = "nonconform"
        self.save(summary_status="nonconform")
        writes = []
        self.run_main(writes)
        table = next(body for path, body in writes if path.name == "integrations.tex")
        self.assertIn("Uvicorn include md & Markdown same size & 0/1 & 1", table)


if __name__ == "__main__":
    unittest.main()
