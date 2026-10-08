import unittest

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
        self.assertEqual(record_signature({"status": "matched"}), "matched")
        self.assertEqual(
            record_signature(
                {
                    "status": "stale",
                    "metrics": {"accepted_events": 1, "failed_builds": 0},
                    "completed_builds": 0,
                }
            ),
            "scheduling_failure",
        )
        self.assertEqual(
            record_signature(
                {
                    "status": "stale",
                    "metrics": {"accepted_events": 1, "failed_builds": 1},
                    "completed_builds": 0,
                }
            ),
            "consumer_failure",
        )
        self.assertEqual(
            record_signature(
                {
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
                {
                    "status": "stale",
                    "metrics": {"accepted_events": 1, "failed_builds": 0},
                    "completed_builds": 1,
                }
            ),
            "unknown_stale",
        )


if __name__ == "__main__":
    unittest.main()
