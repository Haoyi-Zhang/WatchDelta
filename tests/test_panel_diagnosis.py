import unittest

from watchdelta.active_diagnosis import SIGNATURES, hypothesis_space
from watchdelta.panel_diagnosis import (
    decode_nearest,
    exhaustive_single_corruptions,
    minimum_distance,
    signature_vector,
    synthesize_panel,
)


class PanelDiagnosisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.robust = synthesize_panel(1)
        cls.exact = synthesize_panel(0, interventions=cls.robust.panel)

    def test_minimum_cardinality_certificates(self):
        self.assertEqual(self.exact.selected_count, 5)
        self.assertEqual(self.exact.minimum_distance, 1)
        self.assertEqual(self.robust.selected_count, 12)
        self.assertEqual(self.robust.minimum_distance, 3)
        self.assertTrue(self.exact.optimal)
        self.assertTrue(self.robust.optimal)

    def test_exact_panel_decodes_every_hypothesis_without_error(self):
        for truth in hypothesis_space():
            transcript = signature_vector(truth, self.exact.panel)
            decoded = decode_nearest(transcript, self.exact.panel, 0)
            self.assertEqual(decoded.status, "exact")
            self.assertEqual(decoded.hypothesis, truth)

    def test_robust_panel_corrects_every_single_substitution(self):
        alphabet = SIGNATURES + ("unknown_stale",)
        cases = 0
        for truth in hypothesis_space():
            for transcript in exhaustive_single_corruptions(
                truth, self.robust.panel, alphabet=alphabet
            ):
                decoded = decode_nearest(transcript, self.robust.panel, 1)
                self.assertEqual(decoded.status, "exact")
                self.assertEqual(decoded.hypothesis, truth)
                cases += 1
        self.assertEqual(cases, 1920)

    def test_decoder_rejects_two_corruptions_outside_budget_when_not_close(self):
        truth = hypothesis_space()[0]
        transcript = list(signature_vector(truth, self.robust.panel))
        transcript[0] = "unknown_stale"
        transcript[1] = "unknown_stale"
        decoded = decode_nearest(transcript, self.robust.panel, 1)
        self.assertNotEqual(decoded.status, "exact")

    def test_distance_is_independently_recomputed(self):
        self.assertEqual(minimum_distance(self.robust.panel), 3)

    def test_custom_costs_break_cardinality_ties(self):
        from watchdelta.active_diagnosis import intervention_catalog

        catalog = (frozenset(),) + intervention_catalog()
        costs = {item: float(len(item)) for item in catalog}
        certificate = synthesize_panel(0, intervention_costs=costs)
        self.assertEqual(certificate.selected_count, 5)
        self.assertEqual(certificate.objective_cost, 13.0)
        self.assertEqual(certificate.candidate_count, len(catalog))

    def test_two_error_certificate_is_infeasible_for_declared_catalog(self):
        with self.assertRaisesRegex(RuntimeError, "infeasible|Infeasible"):
            synthesize_panel(2)


if __name__ == "__main__":
    unittest.main()
