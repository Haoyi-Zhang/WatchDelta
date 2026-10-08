import unittest
from watchdelta.run import completed_builds

class CompletionTests(unittest.TestCase):
    def test_start_is_not_completion(self):
        self.assertEqual(completed_builds([{'kind':'build_start','t_ns':2}],1,3),0)
    def test_failure_is_not_success(self):
        self.assertEqual(completed_builds([{'kind':'build_end','t_ns':2,'returncode':42}],1,3),0)
    def test_success_and_window(self):
        events=[{'kind':'build_end','t_ns':t,'returncode':0} for t in [1,2,3,4]]
        self.assertEqual(completed_builds(events,1,3),2)
    def test_malformed_completion(self):
        self.assertEqual(completed_builds([{'kind':'build_end','t_ns':2}],1,3),0)
    def test_invalid_window(self):
        with self.assertRaises(ValueError):completed_builds([],4,3)
if __name__=='__main__':unittest.main()
