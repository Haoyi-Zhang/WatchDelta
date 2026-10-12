import unittest
from copy import deepcopy
from tests.test_qualification import valid_record

from watchdelta.active_diagnosis import (
    BOUNDARIES,
    choose_intervention,
    greedy_separating_panel,
    hypothesis_space,
    predict_signature,
    record_signature,
    simulate_active_trace,
    update_candidates,
)
from watchdelta.qualification import qualify
from watchdelta.panel_diagnosis import decode_nearest


class ActiveDiagnosisTests(unittest.TestCase):
    def test_model_has_expected_hypotheses(self):
        hypotheses = hypothesis_space()
        self.assertEqual(len(hypotheses), 32)
        self.assertIn(frozenset(), hypotheses)
        self.assertIn(frozenset(BOUNDARIES[3:]), hypotheses)

    def test_active_planner_exactly_identifies_every_modeled_set(self):
        for truth in hypothesis_space():
            candidates, trace = simulate_active_trace(truth)
            self.assertEqual(candidates, (truth,))
            self.assertLessEqual(len(trace), 5)
            self.assertTrue(all(item["candidates_after"] >= 1 for item in trace))

    def test_planner_is_deterministic(self):
        hypotheses = hypothesis_space()
        first = choose_intervention(hypotheses, [frozenset()])
        second = choose_intervention(hypotheses, [frozenset()])
        self.assertEqual(first, second)

    def test_fixed_panel_separates_all_hypotheses(self):
        hypotheses = hypothesis_space()
        panel = greedy_separating_panel()
        self.assertEqual(len(panel), 6)
        vectors = {
            tuple(predict_signature(hypothesis, repair) for repair in panel)
            for hypothesis in hypotheses
        }
        self.assertEqual(len(vectors), len(hypotheses))

    def test_unknown_signature_eliminates_model_candidates(self):
        candidates = update_candidates(hypothesis_space(), frozenset(), "unknown_stale")
        self.assertEqual(candidates, ())

    def test_record_signature_observables(self):
        self.assertEqual(record_signature(valid_record()), "matched")
        self.assertEqual(
            record_signature(
                {**valid_record(stale=True),
                    "status": "stale",
                    "metrics": {"accepted_events": 1, "failed_builds": 0},
                    "completed_builds": 0,
                }
            ),
            "scheduling_failure",
        )
        self.assertEqual(
            record_signature(
                {**valid_record(stale=True),
                    "status": "stale",
                    "metrics": {"accepted_events": 1, "failed_builds": 1},
                    "completed_builds": 0,
                }
            ),
            "consumer_failure",
        )
        self.assertEqual(
            record_signature(
                {**valid_record(stale=True),
                    "status": "stale",
                    "metrics": {"accepted_events": 1, "failed_builds": 0},
                    "completed_builds": 1,
                    "unpublished_matches_clean": True,
                }
            ),
            "publication_failure",
        )
        self.assertEqual(
            record_signature(
                {**valid_record(stale=True),
                    "status": "stale",
                    "metrics": {"accepted_events": 1, "failed_builds": 0},
                    "completed_builds": 1,
                }
            ),
            "unknown_stale",
        )

    def test_explicit_zero_lifecycle_counts_establish_upstream_silence(self):
        record = valid_record(stale=True)
        record["metrics"] = {"accepted_events": 0, "failed_builds": 0}
        record["completed_builds"] = 0
        self.assertEqual(record_signature(record), "upstream_silence")

    def test_missing_lifecycle_metadata_is_not_observed_silence(self):
        for field in ("metrics", "accepted_events", "failed_builds", "completed_builds"):
            with self.subTest(field=field):
                record = valid_record(stale=True)
                if field in {"accepted_events", "failed_builds"}:
                    del record["metrics"][field]
                else:
                    del record[field]
                self.assertEqual(qualify(record).status, "stale")
                self.assertEqual(record_signature(record), "noncomparable:lifecycle")

    def test_invalid_lifecycle_counters_are_noncomparable(self):
        for field in ("accepted_events", "failed_builds", "completed_builds"):
            for value in (None, False, True, -1, 0.0, "0", [], {}):
                with self.subTest(field=field, value=value):
                    record = valid_record(stale=True)
                    if field == "completed_builds":
                        record[field] = value
                    else:
                        record["metrics"][field] = value
                    self.assertEqual(record_signature(record), "noncomparable:lifecycle")
        for value in (None, [], 0, "missing"):
            with self.subTest(metrics=value):
                record = valid_record(stale=True)
                record["metrics"] = value
                self.assertEqual(record_signature(record), "noncomparable:lifecycle")

    def test_publication_flag_does_not_override_missing_lifecycle(self):
        record = valid_record(stale=True)
        record["unpublished_matches_clean"] = True
        del record["metrics"]["failed_builds"]
        self.assertEqual(record_signature(record), "noncomparable:lifecycle")

    def test_lifecycle_gap_cannot_be_corrected_as_panel_noise(self):
        record = valid_record(stale=True)
        del record["completed_builds"]
        observed = record_signature(record)
        self.assertEqual(update_candidates(hypothesis_space(), frozenset(), observed), ())
        decoded = decode_nearest((observed,), (frozenset(),), 1)
        self.assertEqual(decoded.status, "inconclusive")
        self.assertIsNone(decoded.hypothesis)

    def test_endpoint_agreement_does_not_require_lifecycle_inference(self):
        record = valid_record()
        del record["metrics"]
        del record["completed_builds"]
        self.assertEqual(record_signature(record), "matched")

    def test_failed_endpoint_premises_take_precedence_over_lifecycle(self):
        original = valid_record(stale=True)
        for field in ("ready_ns", "snapshot_stable"):
            with self.subTest(field=field):
                record = deepcopy(original)
                del record[field]
                del record["metrics"]
                self.assertEqual(record_signature(record), "noncomparable:inconclusive")


if __name__ == "__main__":
    unittest.main()
