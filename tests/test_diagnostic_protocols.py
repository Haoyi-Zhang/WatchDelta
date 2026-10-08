import tempfile
import unittest
from pathlib import Path
from watchdelta.core import create_fixture, source_files, build_once, projection
from watchdelta.diagnosis import classify

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
            {'status':'stale','edit':{'obligation':True},'metrics':{'accepted_events':0}},
            {'broad_filter':{'status':'matched','metrics':{}}})
        self.assertEqual(label,'selection_failure')

    def test_publication_signature(self):
        label,_=classify(
            {'status':'stale','edit':{'obligation':True},'metrics':{'builds':1},
             'unpublished_matches_clean':True}, {})
        self.assertEqual(label,'publication_failure')

if __name__ == '__main__': unittest.main()
