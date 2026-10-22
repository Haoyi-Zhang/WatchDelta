"""Owned token fixtures only: no Hypercorn, HTTP, imports of app code, or replay."""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/analyze_integrations.py'
SPEC = importlib.util.spec_from_file_location('hypercorn_analysis_candidate', SCRIPT)
analysis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analysis)


class HypercornQualificationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='owned-hypercorn-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.results = self.root / 'results'
        self.dataset = self.results / 'hypercorn-integration'
        self.case = self.dataset / 'episodes/owned-benign'
        self.case.mkdir(parents=True)
        self.source = b'CONTENT = "WD0000000001"\n'
        digest = hashlib.sha256(self.source).hexdigest()
        self.record = {
            'id': 'owned-benign', 'scenario': 'same_size', 'status': 'matched',
            'initial': 'WD0000000000', 'expected': 'WD0000000001',
            'observed': 'WD0000000001', 'ready_ns': 1, 'endpoint_ns': 4,
            'edit': {'start_ns': 2, 'end_ns': 3, 'obligation': True,
                     'source_sha256': digest, 'mtime_restored': False},
            'source_sha256': digest, 'reload_imports': 1,
            'oracle': {'returncode': 0, 'content': 'WD0000000001',
                       'stdout': 'WATCHDELTA_ORACLE="WD0000000001"\n'},
        }
        self.job = {'id': 'owned-benign', 'scenario': 'same_size'}
        (self.case / 'final-app.py').write_bytes(self.source)
        (self.results / 'derived').mkdir()
        (self.results / 'derived/summary.json').write_text(json.dumps({
            'datasets': {'uvicorn-integration': {'n': 1, 'outcomes': {'matched': 1}}}
        }), encoding='utf-8')
        self.save()

    def save(self):
        raw = json.dumps(self.record)
        (self.dataset / 'records.jsonl').write_text(raw + '\n', encoding='utf-8')
        (self.case / 'record.json').write_text(raw, encoding='utf-8')
        protocol = json.dumps({'id': 'owned', 'jobs': [self.job]})
        (self.dataset / 'protocol.json').write_bytes(protocol.encode())
        (self.dataset / 'protocol.sha256').write_text(
            hashlib.sha256(protocol.encode()).hexdigest(), encoding='utf-8')
        (self.dataset / 'complete.json').write_text('{"episodes": 1}', encoding='utf-8')

    def run_main(self, writes):
        uv = [{'status': 'matched', 'mode': 'include_md', 'scenario': 'same_size'}]
        with patch.object(analysis, 'validate_uvicorn', return_value=uv), \
             patch.object(analysis, 'validate_vite', return_value=([], {'changed': 0})), \
             patch.object(analysis, 'validate_mkdocs', return_value=([], {
                 'burst_events': 0, 'burst_builds': 0})), \
             patch.object(analysis, 'write', side_effect=lambda p, b: writes.append((p, b))), \
             patch('sys.argv', ['analysis', '--results', str(self.results),
                                '--paper', str(self.root / 'paper')]), \
             redirect_stdout(io.StringIO()):
            analysis.main()

    def assert_rejected(self):
        self.save()
        writes = []
        with self.assertRaises(RuntimeError):
            self.run_main(writes)
        self.assertEqual(writes, [])
        self.assertFalse((self.root / 'paper').exists())

    def test_valid_legacy_preserves_record_and_reports_scope(self):
        before = (self.dataset / 'records.jsonl').read_bytes()
        writes = []
        self.run_main(writes)
        summary = json.loads(next(body for path, body in writes
                                  if path.name == 'extensions-summary.json'))
        self.assertEqual(summary['hypercorn']['outcomes'], {'matched': 1})
        self.assertEqual(summary['hypercorn']['reference_evidence'], {
            'legacy-direct-source; frozen-isolation-witness-not-recorded': 1})
        self.assertEqual((self.dataset / 'records.jsonl').read_bytes(), before)
        self.assertNotIn('source_stable', self.record)
        self.assertIn('Hypercorn default & Python same size & 1/1',
                      next(body for path, body in writes if path.name == 'integrations.tex'))

    def test_valid_new_schema_requires_real_frozen_witness(self):
        self.record['source_stable'] = True
        (self.case / 'reference').mkdir()
        (self.case / 'reference/app.py').write_bytes(self.source)
        self.save()
        self.assertEqual(analysis.validate_hypercorn_premises(self.record, self.case),
                         'frozen-source-and-stability-flag')
        writes = []
        self.run_main(writes)
        self.assertTrue(writes)

    def test_valid_legacy_stale_and_control_are_not_reclassified(self):
        for scenario in ('preserved_stat', 'temporary'):
            with self.subTest(scenario=scenario):
                self.record['scenario'] = self.job['scenario'] = scenario
                self.record['reload_imports'] = 0
                if scenario == 'preserved_stat':
                    self.record['observed'] = self.record['initial']
                    self.record['status'] = 'stale'
                    self.record['edit']['mtime_restored'] = True
                else:
                    self.record['initial'] = self.record['expected'] = 'WD0000000000'
                    self.record['observed'] = self.record['initial']
                    self.record['oracle']['content'] = self.record['initial']
                    self.record['oracle']['stdout'] = 'WATCHDELTA_ORACLE="WD0000000000"\n'
                    self.record['status'] = 'matched'
                    self.record['edit']['obligation'] = False
                    source = b'CONTENT = "WD0000000000"\n'
                    (self.case / 'final-app.py').write_bytes(source)
                    self.record['source_sha256'] = self.record['edit']['source_sha256'] = hashlib.sha256(source).hexdigest()
                self.save()
                records, _ = analysis.validate_hypercorn(self.results)
                self.assertEqual(records, [self.record])

    def test_missing_readiness_and_each_clock_is_rejected(self):
        baseline = deepcopy(self.record)
        for key in ('initial', 'ready_ns', 'endpoint_ns', 'start_ns', 'end_ns'):
            with self.subTest(key=key):
                self.record = deepcopy(baseline)
                del (self.record['edit'] if key in ('start_ns', 'end_ns') else self.record)[key]
                self.assert_rejected()

    def test_inverted_clock_boundaries_are_rejected(self):
        baseline = deepcopy(self.record)
        for clocks in ((3, 2, 3, 4), (1, 3, 2, 4), (1, 2, 5, 4)):
            with self.subTest(clocks=clocks):
                self.record = deepcopy(baseline)
                self.record['ready_ns'], self.record['edit']['start_ns'], \
                    self.record['edit']['end_ns'], self.record['endpoint_ns'] = clocks
                self.assert_rejected()

    def test_boolean_or_nonpositive_clock_is_rejected(self):
        for value in (True, 0, -1, 1.0, '1'):
            with self.subTest(value=value):
                self.record['ready_ns'] = value
                self.assert_rejected()

    def test_wrong_initial_http_token_is_rejected(self):
        self.record['initial'] = 'unexpected'
        self.assert_rejected()

    def test_explicit_unstable_or_nonboolean_source_is_rejected(self):
        for value in (False, None, 1, 'true'):
            with self.subTest(value=value):
                self.record['source_stable'] = value
                self.assert_rejected()

    def test_new_schema_without_frozen_source_is_rejected(self):
        self.record['source_stable'] = True
        self.assert_rejected()

    def test_new_schema_different_frozen_source_is_rejected(self):
        self.record['source_stable'] = True
        (self.case / 'reference').mkdir()
        (self.case / 'reference/app.py').write_bytes(b'CONTENT = "different"\n')
        self.assert_rejected()

    def test_missing_or_failed_reference_exit_is_rejected(self):
        for value in (None, False, 7):
            with self.subTest(value=value):
                self.record['oracle']['returncode'] = value
                self.assert_rejected()
        del self.record['oracle']['returncode']
        self.assert_rejected()

    def test_contradictory_oracle_payload_is_rejected(self):
        self.record['oracle']['content'] = 'different'
        self.assert_rejected()

    def test_bad_oracle_stdout_is_rejected(self):
        for value in ('', 'WATCHDELTA_ORACLE=invalid',
                      'WATCHDELTA_ORACLE="different"',
                      'WATCHDELTA_ORACLE="WD0000000001"\n' * 2):
            with self.subTest(value=value):
                self.record['oracle']['stdout'] = value
                self.assert_rejected()

    def test_reference_and_expected_cannot_disagree_with_source(self):
        self.record['oracle']['content'] = self.record['expected'] = 'different'
        self.record['oracle']['stdout'] = 'WATCHDELTA_ORACLE="different"\n'
        self.assert_rejected()

    def test_inconsistent_edit_source_hash_is_rejected(self):
        self.record['edit']['source_sha256'] = 'different'
        self.assert_rejected()

    def test_retained_source_change_is_rejected(self):
        (self.case / 'final-app.py').write_bytes(b'CONTENT = "different"\n')
        self.assert_rejected()

    def test_inconsistent_obligation_is_rejected(self):
        self.record['edit']['obligation'] = False
        self.assert_rejected()

    def test_missing_terminal_capture_is_rejected(self):
        del self.record['observed']
        self.assert_rejected()


if __name__ == '__main__':
    unittest.main()
