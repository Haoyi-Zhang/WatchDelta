"""Benign combined-analysis regressions; no retained data or campaigns are written."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import analyze_compound_scaling as analysis
from scripts import analyze_diagnostics
from tests.test_qualification import valid_record
from watchdelta.qualification import qualify

ROOT = Path(__file__).resolve().parents[1]


def scaling_records(sizes):
    records = []
    for tool, mode in (("tsc", "default"), ("tsc", "hash"),
                       ("docs", "relevant"), ("docs", "hash")):
        for size in sizes:
            record = valid_record()
            record.update(id=f"{tool}-{mode}-{size}", tool=tool, mode=mode,
                          file_count=size, stable_latency_ms=12.0,
                          setup_to_ready_ms=100.0)
            record["metrics"].update(cpu_s=.01, scan_bytes=256)
            if tool == "tsc":
                for owner, field in ((record, "initial_projection"),
                                     (record, "observed_projection"),
                                     (record["clean"], "projection")):
                    owner[field] = {"index.js": next(iter(owner[field].values()))}
                record["runtime"] = {"returncode": 0, "stdout": "terminal", "stderr": ""}
                record["clean_runtime"] = deepcopy(record["runtime"])
                record["runtime_matches"] = True
            records.append(record)
    return records


class ScalingEligibilityTests(unittest.TestCase):
    def test_retained_small_scaling_remains_eligible(self):
        records = analysis.load_scaling_small(ROOT / "results")
        self.assertEqual(len(records), 48)
        self.assertTrue(all(qualify(record).status == "matched" for record in records))

    def test_small_loader_rejects_missing_invalid_and_inconclusive_premises(self):
        original_loads = json.loads
        target = "overlay-tsc-default-n10-r01"
        mutations = ("reference_exit", "missing_reference", "missing_snapshot",
                     "invalid_clock", "missing_status", "inconclusive_status")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                def read(text, *args, **kwargs):
                    value = original_loads(text, *args, **kwargs)
                    if isinstance(value, dict) and value.get("id") == target:
                        if mutation == "reference_exit": value["clean"]["returncode"] = 7
                        if mutation == "missing_reference": del value["clean"]
                        if mutation == "missing_snapshot": del value["snapshot_stable"]
                        if mutation == "invalid_clock": value["ready_ns"] = value["edit"]["end_ns"] + 1
                        if mutation == "missing_status": del value["status"]
                        if mutation == "inconclusive_status": value["status"] = "inconclusive"
                    return value
                # Both JSON mirrors are changed only as they are read into memory.
                with patch.object(analyze_diagnostics.json, "loads", side_effect=read):
                    with self.assertRaises(RuntimeError):
                        analysis.load_scaling_small(ROOT / "results")

    def test_small_loader_requires_completion_marker(self):
        original = Path.read_text
        def read(path, *args, **kwargs):
            if path == ROOT / "results/scaling-small/complete.json":
                raise FileNotFoundError("completion marker missing")
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", new=read):
            with self.assertRaises(FileNotFoundError):
                analysis.load_scaling_small(ROOT / "results")

    def test_small_loader_rejects_inconsistent_completion_count(self):
        original = Path.read_text
        def read(path, *args, **kwargs):
            if path == ROOT / "results/scaling-small/complete.json":
                return json.dumps({"episodes": 47})
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", new=read):
            with self.assertRaisesRegex(RuntimeError, "completion"):
                analysis.load_scaling_small(ROOT / "results")

    def test_aggregation_preserves_qualified_counts_and_measurements(self):
        small = scaling_records((10, 250))
        large = scaling_records((1000, 5000))
        original = deepcopy((small, large))
        rows = analysis.aggregate_scaling(small, large)
        self.assertEqual(len(rows), 16)
        self.assertEqual(sum(row["n"] for row in rows), 16)
        self.assertEqual(sum(row["matched"] for row in rows), 16)
        self.assertTrue(all(row["latency_median_ms"] == 12.0 for row in rows))
        self.assertEqual((small, large), original)

    def test_aggregation_cannot_bypass_endpoint_qualification(self):
        for cohort in ("small", "large"):
            for mutation in ("reference_exit", "snapshot", "status", "schema"):
                with self.subTest(cohort=cohort, mutation=mutation):
                    small = scaling_records((10, 250))
                    large = scaling_records((1000, 5000))
                    selected = small if cohort == "small" else large
                    if mutation == "reference_exit": selected[0]["clean"]["returncode"] = 7
                    if mutation == "snapshot": del selected[0]["snapshot_stable"]
                    if mutation == "status": selected[0]["status"] = "inconclusive"
                    if mutation == "schema": selected[0]["clean"] = None
                    with self.assertRaisesRegex(RuntimeError, "scaling endpoint"):
                        analysis.aggregate_scaling(small, large)

    def test_missing_scaling_cell_is_not_dropped_from_denominator(self):
        with self.assertRaisesRegex(RuntimeError, "missing scaling cell"):
            analysis.aggregate_scaling([], scaling_records((1000, 5000)))

    def test_cli_rejects_ineligible_input_before_output_generation(self):
        small = scaling_records((10, 250))
        small[0]["clean"]["returncode"] = 7
        with tempfile.TemporaryDirectory() as directory:
            paper = Path(directory) / "paper"
            with patch.object(analysis, "validate_compound", return_value=([], {})), \
                 patch.object(analysis, "validate_scaling_large", return_value=(scaling_records((1000, 5000)), {})), \
                 patch.object(analysis, "load_scaling_small", return_value=small), \
                 patch.object(analysis, "render_outputs", return_value={}) as render, \
                 patch("sys.argv", ["analyze_compound_scaling", "--results", str(ROOT / "results"), "--paper", str(paper)]), \
                 redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "scaling endpoint"):
                    analysis.main()
            render.assert_not_called()
            self.assertFalse(paper.exists())

    def test_rendered_totals_use_eligible_aggregate_rows(self):
        rows = analysis.aggregate_scaling(scaling_records((10, 250)), scaling_records((1000, 5000)))
        truths = (("scheduling", "consumer"),
                  ("scheduling", "consumer", "publication"),
                  ("selection", "scheduling", "consumer", "publication"))
        units = [{"supported": True, "truth": list(truth), "outcome": "exact", "executions": 2}
                 for truth in truths]
        units.append({"supported": False, "truth": ["post_build_corruption"], "outcome": "unmodeled", "executions": 1})
        summary = {"units": 4, "known_units": 3, "known_exact": 3, "unknown_units": 1,
                   "unknown_unmodeled": 1, "actual_process_executions": 7,
                   "episodes_known_median": 2, "episodes_known_max": 2, "fixed_panel_size": 6}
        def read(path, *args, **kwargs):
            if path.name == "diagnostics-summary.json": return json.dumps({"runtime_total": 0})
            if path.name == "extensions-summary.json": return json.dumps({"vite": {"cases": 0}, "mkdocs": {"episodes": 0}})
            raise AssertionError(f"unexpected read: {path}")
        with patch.object(Path, "read_text", new=read), patch.object(analysis, "write"):
            derived = analysis.render_outputs(Path("unused-paper"), Path("unused-results"),
                                              units, summary, {"episodes": 8, "matched": 8}, rows)
        self.assertEqual(derived["macros"]["ScaleAllN"], 16)
        self.assertEqual(derived["macros"]["ScaleAllMatchedN"], 16)


if __name__ == "__main__":
    unittest.main()
