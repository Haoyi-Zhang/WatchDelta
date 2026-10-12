import tempfile
import unittest
from pathlib import Path
from watchdelta.core import create_fixture, source_files, build_once, projection
from watchdelta.diagnosis import classify
from tests.test_qualification import valid_record

class V3ProtocolTests(unittest.TestCase):
    def test_fixture_file_counts_are_exact(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'docs'; create_fixture(root,'docs','relevant',10)
            self.assertEqual(len(source_files(root,'docs')),10)
            build_once(root,'docs'); self.assertEqual(len(projection(root/'out','.html')),10)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'ts'; create_fixture(root,'tsc','default',10)
            self.assertEqual(len(source_files(root,'tsc')),10)
            result=build_once(root,'tsc'); self.assertEqual(result.returncode,0)
            self.assertEqual(len(projection(root/'out','.js')),10)

    def test_diagnosis_refuses_to_guess(self):
        label,reasons=classify({'status':'stale','edit':{'obligation':True},'metrics':{}},{})
        self.assertEqual(label,'unresolved')
        self.assertTrue(reasons)

    def test_selection_signature(self):
        label,_=classify(
            {**valid_record(stale=True),'metrics':{'accepted_events':0,'failed_builds':0}},
            {'broad_filter':{**valid_record(),'metrics':{}}})
        self.assertEqual(label,'selection_failure')

    def test_publication_signature(self):
        label,_=classify(
            {**valid_record(stale=True),'metrics':{'builds':1,'accepted_events':1,'failed_builds':0},
             'unpublished_matches_clean':True}, {})
        self.assertEqual(label,'publication_failure')

    def test_missing_completion_is_not_scheduling_failure(self):
        record = valid_record(stale=True)
        del record['completed_builds']
        label, reasons = classify(record, {})
        self.assertEqual(label, 'unresolved')
        self.assertIn('lifecycle', reasons[0])

    def test_missing_lifecycle_is_not_repaired_by_a_matching_intervention(self):
        record = valid_record(stale=True)
        del record['metrics']['failed_builds']
        label, reasons = classify(record, {'broad_filter': valid_record()})
        self.assertEqual(label, 'unresolved')
        self.assertIn('lifecycle', reasons[0])

    def test_invalid_intervention_lifecycle_is_unresolved(self):
        intervention = valid_record(stale=True)
        intervention['metrics']['accepted_events'] = False
        label, reasons = classify(valid_record(stale=True), {'broad_filter': intervention})
        self.assertEqual(label, 'unresolved')
        self.assertIn('lifecycle', reasons[0])

if __name__ == '__main__': unittest.main()
