"""Benign endpoint/schema regressions, including the mandatory analyzer path."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
import io
from unittest.mock import patch

from watchdelta.core import source_fingerprint
from watchdelta.qualification import qualify, validate_retained
from watchdelta.active_diagnosis import record_signature, hypothesis_space, predict_signature
from watchdelta.panel_diagnosis import decode_nearest
from scripts.analyze import load
from scripts import analyze_panel


def valid_record(*, stale=False):
    expected = {"index.html": hashlib.sha256(b"new").hexdigest()}
    observed = {"index.html": hashlib.sha256(b"old" if stale else b"new").hexdigest()}
    return {"id": "benign", "tool": "docs", "mode": "relevant", "scenario": "same_size",
            "status": "stale" if stale else "matched", "ready_ns": 1,
            "edit": {"start_ns": 2, "end_ns": 3, "obligation": True},
            "snapshot_stable": True, "obligation_consistent": True,
            "initial_projection": {"index.html": hashlib.sha256(b"initial").hexdigest()},
            "observed_projection": observed, "served_projection": deepcopy(observed),
            "served_matches_disk": True, "clean": {"returncode": 0, "projection": expected,
                                                       "source_sha256": "checked-by-validator"},
            "metrics": {"accepted_events": 1, "failed_builds": 0}, "completed_builds": 1}


class QualificationTests(unittest.TestCase):
    def test_valid_and_stale_are_distinct_from_inconclusive(self):
        self.assertEqual(qualify(valid_record()).verdict, "conform")
        self.assertEqual(qualify(valid_record(stale=True)).verdict, "nonconform")

    def test_reference_failure_cannot_match_or_reach_diagnosis(self):
        record = valid_record()
        record["clean"]["returncode"] = 7
        self.assertEqual(qualify(record).status, "inconclusive")
        self.assertEqual(record_signature(record), "noncomparable:inconclusive")

    def test_missing_and_false_premises_are_not_true(self):
        for field in ("snapshot_stable", "ready_ns", "served_matches_disk", "obligation_consistent"):
            for value in (None, False):
                record = valid_record()
                if value is None:
                    del record[field]
                else:
                    record[field] = value
                if field == "served_matches_disk" and value is False:
                    record["served_projection"] = {"index.html": "different"}
                    self.assertEqual(qualify(record).status, "nonconform")
                else:
                    self.assertEqual(qualify(record).status, "inconclusive", (field, value))

    def test_service_disk_mismatch_is_nonconform_not_reference_failure(self):
        record = valid_record()
        record["served_projection"] = {"index.html": "stale-service"}
        record["served_matches_disk"] = False
        self.assertEqual(qualify(record).status, "nonconform")
        record["status"] = "nonconform"
        self.assertEqual(record_signature(record), "unknown_stale")

    def test_forged_http_flag_does_not_override_bytes(self):
        record = valid_record()
        record["served_projection"] = {"index.html": "stale-service"}
        self.assertEqual(qualify(record).status, "inconclusive")

    def test_obligation_and_clock_are_checked(self):
        record = valid_record()
        record["ready_ns"] = 4
        self.assertEqual(qualify(record).status, "inconclusive")
        record = valid_record()
        record["edit"]["obligation"] = False
        self.assertEqual(qualify(record).status, "inconclusive")

    def test_noncomparable_is_not_a_correctable_signature_substitution(self):
        panel = (frozenset(), frozenset({"selection"}))
        observed = ("noncomparable:inconclusive", predict_signature(hypothesis_space()[0], panel[1]))
        self.assertEqual(decode_nearest(observed, panel, 1).status, "inconclusive")

    def test_typescript_consumer_failure_with_matching_disk_is_nonconform(self):
        record = valid_record()
        record.update(tool="tsc", runtime={"returncode": 1}, clean_runtime={"returncode": 0}, runtime_matches=False)
        self.assertEqual(qualify(record).status, "nonconform")

    def test_primary_loader_does_not_skip_recorded_oracle_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "cases"
            case = folder / "episodes/benign"
            case.mkdir(parents=True)
            record = valid_record()
            record["status"] = "oracle_error"
            record["clean"]["returncode"] = 9
            raw = json.dumps({"jobs": [{"id": "benign"}]})
            (folder / "protocol.json").write_text(raw)
            (folder / "protocol.sha256").write_text(hashlib.sha256(raw.encode()).hexdigest())
            (folder / "complete.json").write_text("{}")
            (folder / "records.jsonl").write_text(json.dumps(record))
            (case / "record.json").write_text(json.dumps(record))
            with self.assertRaisesRegex(RuntimeError, "reference did not exit successfully"):
                load("cases", Path(tmp))

    def test_retained_source_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            record = valid_record()
            for tree in ("work", "clean"):
                (folder / tree / "src").mkdir(parents=True)
                (folder / tree / "src/index.md").write_text("final")
            for tree in ("observed", "clean/out"):
                (folder / tree).mkdir(parents=True, exist_ok=True)
                (folder / tree / "index.html").write_bytes(b"new")
            record["clean"]["source_sha256"] = source_fingerprint(folder / "work", "docs")[0]
            self.assertEqual(validate_retained(record, folder).status, "matched")
            (folder / "work/src/index.md").write_text("drift")
            with self.assertRaisesRegex(RuntimeError, "terminal source differs"):
                validate_retained(record, folder)

    def test_panel_cli_rejects_bad_premises_and_never_writes_success_macros(self):
        # Reanalyze retained benign fixtures with one in-memory corrupted record.
        # No archived record or protocol is edited, and no watcher is launched.
        results = Path(__file__).resolve().parents[1] / "results"
        original = analyze_panel.read_json
        mutations = ("clean_exit", "snapshot", "service", "source")
        with tempfile.TemporaryDirectory() as tmp:
            for mutation in mutations:
                def read(path):
                    value = original(path)
                    if path.name == "record.json" and path.parent.name == "panel-h00--s00-none":
                        if mutation == "clean_exit": value["clean"]["returncode"] = 8
                        if mutation == "snapshot": value["snapshot_stable"] = False
                        if mutation == "service":
                            value["served_projection"] = {"index.html": "different"}
                            value["served_matches_disk"] = False
                        if mutation == "source": value["clean"]["source_sha256"] = "different"
                    return value
                paper = Path(tmp) / mutation
                output = io.StringIO()
                with patch.object(analyze_panel, "read_json", side_effect=read), \
                     patch("sys.argv", ["analyze_panel", "--results", str(results), "--paper", str(paper)]), \
                     redirect_stdout(output):
                    self.assertEqual(analyze_panel.main(), 1)
                report = json.loads(output.getvalue())
                self.assertTrue(report["errors"])
                self.assertEqual(report["recomputed"]["model_conformant_executions"], 383)
                self.assertEqual(report["recomputed"]["model_conformant_units"], 31)
                self.assertEqual(report["recomputed"]["robust_zero_error_recovered"], 31)
                self.assertFalse(paper.exists(), mutation)
