"""Small Linux regression replay; not a replacement for the retained full study."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from watchdelta.core import module_subprocess_env


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'linux':
        raise SystemExit('Actual-process replay requires Linux process groups and /proc')
    args.output.mkdir(parents=True, exist_ok=False)
    jobs = [
        dict(id='docs-relevant-atomic', numeric_id=1, tool='docs', mode='relevant', scenario='atomic'),
        dict(id='docs-content-restored-time', numeric_id=2, tool='docs', mode='hash', scenario='preserved_stat'),
        dict(id='tsc-native-atomic', numeric_id=3, tool='tsc', mode='default', scenario='atomic'),
        dict(id='tsc-content-restored-time', numeric_id=4, tool='tsc', mode='hash', scenario='preserved_stat'),
    ]
    protocol = args.output / 'watch-protocol.json'
    protocol.write_text(json.dumps(dict(jobs=jobs, settle_seconds=5.0), indent=2), encoding='utf-8')
    destination = args.output / 'watch'
    subprocess.run([sys.executable, '-m', 'watchdelta.run', '--protocol', str(protocol),
                    '--output', str(destination)], cwd=ROOT, env=module_subprocess_env(),
                   check=True, timeout=180)
    records = [json.loads(line) for line in (destination / 'records.jsonl').read_text().splitlines()]
    assert len(records) == len(jobs)
    for record in records:
        assert record['status'] == 'matched', record
        assert record['snapshot_stable'] and record['obligation_consistent'], record
        if record['tool'] == 'docs':
            assert record['served_matches_disk'], record
        else:
            assert record['runtime_matches'], record
        assert record['metrics_include_http_probes'] is False
    integration = args.output / 'hypercorn-protocol.json'
    integration.write_text(json.dumps(dict(settle_seconds=3.0, jobs=[
        dict(id='hypercorn-same-size', numeric_id=5, scenario='same_size'),
        dict(id='hypercorn-restored-time', numeric_id=6, scenario='preserved_stat'),
    ]), indent=2), encoding='utf-8')
    output = args.output / 'hypercorn'
    subprocess.run([sys.executable, 'scripts/hypercorn_integration.py', '--protocol', str(integration),
                    '--output', str(output)], cwd=ROOT, check=True, timeout=120)
    records = [json.loads(line) for line in (output / 'records.jsonl').read_text().splitlines()]
    assert len(records) == 2
    for record in records:
        assert record['source_stable'] and record['oracle']['returncode'] == 0, record
        assert record['status'] == ('stale' if record['scenario'] == 'preserved_stat' else 'matched'), record
    print('Four watch episodes and two real Hypercorn reload episodes passed.')


if __name__ == '__main__':
    main()
