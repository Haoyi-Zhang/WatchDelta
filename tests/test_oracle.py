"""Adversarial tests for the actual output oracle (not event-delivery simulations)."""
import json,tempfile,unittest
from pathlib import Path
from watchdelta.core import projection,endpoint_status,stable_latency,source_fingerprint,create_fixture,build_once,TOKEN0
from watchdelta.replay import edit

class OracleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_same_length_difference_is_not_normalized(self):
        a=self.root/'a';b=self.root/'b';a.mkdir();b.mkdir()
        (a/'index.html').write_text('WD0000000000');(b/'index.html').write_text('WD0000000001')
        self.assertEqual(endpoint_status(projection(a,'.html'),projection(b,'.html'),True),'stale')
    def test_missing_file(self):
        a=self.root/'a';b=self.root/'b';a.mkdir();b.mkdir();(b/'index.html').write_text('x')
        self.assertEqual(endpoint_status(projection(a,'.html'),projection(b,'.html'),True),'stale')
    def test_extra_file(self):
        self.assertEqual(endpoint_status({'x':'a','y':'b'},{'x':'a'},True),'stale')
    def test_path_identity(self):
        self.assertEqual(endpoint_status({'a/x':'h'},{'b/x':'h'},True),'stale')
    def test_failed_oracle_cannot_match(self):
        self.assertEqual(endpoint_status({}, {}, False),'oracle_error')
    def test_intermediate_match_does_not_count(self):
        x={'x':'x'};y={'x':'y'}
        self.assertEqual(stable_latency([{'t_ns':0,'projection':y},{'t_ns':20_000_000,'projection':x},{'t_ns':40_000_000,'projection':y},{'t_ns':60_000_000,'projection':x}],x,10_000_000,True),50)
    def test_final_mismatch_censors_latency(self):
        self.assertIsNone(stable_latency([{'t_ns':0,'projection':{'a':'x'}}],{'a':'y'},0,True))
    def test_noop_has_no_latency(self):
        self.assertIsNone(stable_latency([{'t_ns':0,'projection':{}}],{},0,False))
    def test_precompletion_latency_clamped(self):
        self.assertEqual(stable_latency([{'t_ns':0,'projection':{}}],{},1_000_000,True),0)
    def test_stat_preservation_does_not_fool_content_digest(self):
        create_fixture(self.root/'p','docs','default');p=self.root/'p';before=source_fingerprint(p,'docs')[0]
        stat=(p/'src/index.md').stat();edit(p,'docs','preserved_stat','WD0000000001')
        self.assertEqual(stat.st_mtime_ns,(p/'src/index.md').stat().st_mtime_ns)
        self.assertEqual(stat.st_size,(p/'src/index.md').stat().st_size)
        self.assertNotEqual(before,source_fingerprint(p,'docs')[0])
    def test_temporary_control_is_neutral(self):
        create_fixture(self.root/'p','docs','default');p=self.root/'p';build_once(p,'docs');before=projection(p/'out','.html')
        edit(p,'docs','temporary','WD0000000001');build_once(p,'docs')
        self.assertEqual(before,projection(p/'out','.html'))
    def test_renderer_deterministic(self):
        create_fixture(self.root/'p','docs','default');p=self.root/'p';build_once(p,'docs');before=projection(p/'out','.html');build_once(p,'docs')
        self.assertEqual(before,projection(p/'out','.html'))
    def test_missing_directory_output_is_detected(self):
        create_fixture(self.root/'p','docs','default');p=self.root/'p';build_once(p,'docs');before=projection(p/'out','.html')
        edit(p,'docs','newdir','WD0000000001');build_once(p,'docs')
        self.assertNotEqual(before,projection(p/'out','.html'))
    def test_symlink_rejected(self):
        d=self.root/'out';d.mkdir();(self.root/'x.html').write_text('x');(d/'s.html').symlink_to(self.root/'x.html')
        with self.assertRaises(ValueError):projection(d,'.html')
    def test_size_changing_save_distinct(self):
        create_fixture(self.root/'p','docs','default');p=self.root/'p';before=(p/'src/index.md').stat().st_size
        edit(p,'docs','inplace','WD0000000001');self.assertNotEqual(before,(p/'src/index.md').stat().st_size)
    def test_same_size_save_distinct(self):
        create_fixture(self.root/'p','docs','default');p=self.root/'p';before=(p/'src/index.md').stat().st_size
        edit(p,'docs','same_size','WD0000000001');self.assertEqual(before,(p/'src/index.md').stat().st_size)
if __name__=='__main__':unittest.main()
