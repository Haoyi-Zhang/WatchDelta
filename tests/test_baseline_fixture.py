from pathlib import Path
import importlib.util


def test_documented_baseline_forwards_scaling_fixture_size(tmp_path):
    from watchdelta import run
    original = run.create_fixture
    path = Path(__file__).resolve().parents[1]/'scripts/baseline_challenge.py'
    spec = importlib.util.spec_from_file_location('_watchdelta_baseline', path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        module.documented(tmp_path/'fixture', 'tsc', 'documented_sync', 7)
        assert len(list((tmp_path/'fixture/src').rglob('*.ts'))) == 7
        assert 'synchronousWatchDirectory' in (tmp_path/'fixture/tsconfig.json').read_text()
    finally:
        run.create_fixture = original
