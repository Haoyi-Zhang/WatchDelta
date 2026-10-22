"""Small routing fixtures for the real paper entrypoint; no compiler or subject."""
import importlib.util
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / 'paper/build.py'
build = None
if SCRIPT.is_file():
    SPEC = importlib.util.spec_from_file_location('paper_build_candidate', SCRIPT)
    build = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(build)


@unittest.skipUnless(SCRIPT.is_file(), 'Requires the companion paper directory')
class PaperBuildRouteTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='owned-paper-route-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.paper = self.root / 'paper'
        (self.paper / 'figures').mkdir(parents=True)
        (self.paper / 'generated').mkdir()
        self.data = self.paper / 'generated/scaling-latency.dat'
        self.data.write_text('owned fixture A', encoding='utf-8')
        self.fonts = self.root / 'fonts'
        for relative in ('afm/urw/times/utmr8a.afm', 'type1/urw/times/utmr8a.pfb'):
            path = self.fonts / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture; never used as a font')
        (self.paper / 'main.pdf').write_bytes(b'original fixture')

    def run_build(self, *, fail_renderer=False, automatic_font=False):
        calls = []

        def run(command, **kwargs):
            calls.append((command, kwargs))
            if '-var-value=TEXMFDIST' in command:
                return subprocess.CompletedProcess(command, 0, stdout=str(self.root))
            if str(command[1]).endswith('draw_scaling.py'):
                if fail_renderer:
                    raise subprocess.CalledProcessError(1, command)
                (self.paper / 'figures/scaling.pdf').write_bytes(self.data.read_bytes())
            elif command[0] == 'pdflatex':
                work = Path(kwargs['cwd'])
                self.assertEqual((work / 'figures/scaling.pdf').read_bytes(), self.data.read_bytes())
                (work / 'main.log').write_text('fixture clean log', encoding='utf-8')
                (work / 'main.pdf').write_bytes(b'fixture compiled')
            return subprocess.CompletedProcess(command, 0)

        argv = [] if automatic_font else ['--font-root', str(self.fonts)]
        with patch.object(build, 'HERE', self.paper), \
             patch.object(build.shutil, 'which', side_effect=lambda name: name), \
             patch.object(build.subprocess, 'run', side_effect=run):
            build.main(argv)
        return calls

    def test_missing_and_stale_figure_are_regenerated_before_copy(self):
        for data in ('owned fixture A', 'owned fixture B'):
            with self.subTest(data=data):
                self.data.write_text(data, encoding='utf-8')
                calls = self.run_build()
                render = next(i for i, (cmd, _) in enumerate(calls)
                              if str(cmd[1]).endswith('draw_scaling.py'))
                latex = next(i for i, (cmd, _) in enumerate(calls) if cmd[0] == 'pdflatex')
                self.assertLess(render, latex)
                self.assertIn(str(self.fonts), calls[render][0])
                self.assertEqual((self.paper / 'figures/scaling.pdf').read_text(), data)
                self.assertTrue(all(kwargs['timeout'] <= 180 for _, kwargs in calls))

    def test_renderer_failure_blocks_compilation_and_pdf_replacement(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_build(fail_renderer=True)
        self.assertEqual((self.paper / 'main.pdf').read_bytes(), b'original fixture')

    def test_missing_font_blocks_all_producers(self):
        with patch.object(build.subprocess, 'run') as run, self.assertRaises(SystemExit):
            build.main(['--font-root', str(self.root / 'absent')])
        run.assert_not_called()

    def test_existing_no_argument_route_locates_installed_font_tree(self):
        calls = self.run_build(automatic_font=True)
        self.assertEqual(calls[0][0], ['kpsewhich', '-var-value=TEXMFDIST'])

    @unittest.skipUnless(os.environ.get('WATCHDELTA_TEST_FONT_ROOT'), 'explicit installed font root not supplied')
    def test_real_renderer_changes_only_owned_fixture_when_input_changes(self):
        original = SCRIPT.parent
        renderer = self.paper / 'figures/draw_scaling.py'
        shutil.copy2(original / 'figures/draw_scaling.py', renderer)
        for name in ('latency', 'cpu'):
            shutil.copy2(original / f'generated/scaling-{name}.dat',
                         self.paper / f'generated/scaling-{name}.dat')
        original_hash = hashlib.sha256((original / 'generated/scaling-latency.dat').read_bytes()).hexdigest()
        command = [sys.executable, '-B', str(renderer), '--font-root',
                   os.environ['WATCHDELTA_TEST_FONT_ROOT']]
        subprocess.run(command, check=True, capture_output=True, timeout=180)
        first = hashlib.sha256((self.paper / 'figures/scaling.pdf').read_bytes()).hexdigest()
        fixture_data = self.data.read_text(encoding='utf-8')
        self.assertIn('266.840674', fixture_data)
        self.data.write_text(fixture_data.replace('266.840674', '300.000000'), encoding='utf-8')
        subprocess.run(command, check=True, capture_output=True, timeout=180)
        second = hashlib.sha256((self.paper / 'figures/scaling.pdf').read_bytes()).hexdigest()
        self.assertNotEqual(first, second)
        self.assertEqual(hashlib.sha256((original / 'generated/scaling-latency.dat').read_bytes()).hexdigest(), original_hash)


if __name__ == '__main__':
    unittest.main()
