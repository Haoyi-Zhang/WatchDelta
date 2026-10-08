#!/usr/bin/env python3
"""Run the frozen tree-size and local-filesystem scaling protocol."""
from __future__ import annotations
import argparse, hashlib, json, shutil, subprocess, tempfile, time
from pathlib import Path

# Permit direct execution from an unpacked source tree without relying on an
# inherited PYTHONPATH.  Experiment semantics are unchanged.
import sys as _sys
from pathlib import Path as _BootstrapPath
_SRC = _BootstrapPath(__file__).resolve().parents[1] / "src"
if str(_SRC) not in _sys.path:
    _sys.path.insert(0, str(_SRC))
from watchdelta.run import episode, environment

SIZES=[10,250]
REPETITIONS=3

def mount(path:Path)->dict:
    text=subprocess.check_output(['findmnt','-T',str(path),'-J','-o','TARGET,SOURCE,FSTYPE,OPTIONS'],text=True)
    return json.loads(text)['filesystems'][0]

def jobs()->list[dict]:
    result=[]; numeric=900000
    for filesystem in ['overlay','tmpfs']:
      for tool,modes in [('tsc',['default','hash']),('docs',['relevant','hash'])]:
       for mode in modes:
        for n in SIZES:
         for rep in range(1,REPETITIONS+1):
          result.append({'id':f'{filesystem}-{tool}-{mode}-n{n}-r{rep:02d}',
            'numeric_id':numeric,'filesystem':filesystem,'tool':tool,'mode':mode,
            'scenario':'same_size','inject':'none','diagnostic':False,'file_count':n})
          numeric+=1
    return result

def summarize(output: Path, planned: list[dict]) -> dict:
    records=[json.loads(x) for x in (output/'records.jsonl').read_text().splitlines() if x.strip()]
    summary={'episodes':len(records),'planned_episodes':len(planned),
             'matched':sum(r['status']=='matched' for r in records),
             'stale':sum(r['status']=='stale' for r in records),
             'infrastructure_error':sum(r['status']=='infrastructure_error' for r in records),
             'completed_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    if len(records)==len(planned):
        (output/'complete.json').write_text(json.dumps({'episodes':len(records),'completed_utc':summary['completed_utc']},indent=2)+'\n')
    return summary

def main()->None:
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--protocol',type=Path);p.add_argument('--settle',type=float)
    p.add_argument('--resume',action='store_true');p.add_argument('--max-jobs',type=int);a=p.parse_args()
    if a.protocol:
        raw=a.protocol.read_bytes();protocol=json.loads(raw);plan=protocol['jobs']
        if a.settle is not None and a.settle != protocol['settle_seconds']:
            raise SystemExit('--settle disagrees with frozen protocol')
        settle=float(protocol['settle_seconds'])
    else:
        settle=2.0 if a.settle is None else a.settle;plan=jobs()
        protocol={'id':'scaling-small','settle_seconds':settle,'sizes':SIZES,
                  'repetitions_per_filesystem':REPETITIONS,'jobs':plan}
        raw=(json.dumps(protocol,indent=2,sort_keys=True)+'\n').encode()
    if a.output.exists():
        if not a.resume: raise SystemExit(f'Refusing existing output: {a.output}')
        if (a.output/'protocol.json').read_bytes()!=raw: raise SystemExit('Resume protocol differs')
    else:
        a.output.mkdir(parents=True)
        (a.output/'protocol.json').write_bytes(raw);(a.output/'protocol.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
        env=environment(); env['mounts']={'overlay':mount(a.output),'tmpfs':mount(Path('/dev/shm'))}
        (a.output/'environment.json').write_text(json.dumps(env,indent=2)+'\n')
        (a.output/'records.jsonl').write_text('')
    records=[json.loads(x) for x in (a.output/'records.jsonl').read_text().splitlines() if x.strip()]
    completed={r['id'] for r in records}; pending=[j for j in plan if j['id'] not in completed]
    if a.max_jobs is not None: pending=pending[:a.max_jobs]
    tmpbase=Path(tempfile.mkdtemp(prefix='watchdelta-scaling-',dir='/dev/shm'))
    try:
      with (a.output/'records.jsonl').open('a') as out:
       for i,job in enumerate(pending,1):
        base=a.output if job['filesystem']=='overlay' else tmpbase
        target=a.output/'episodes'/job['id']
        if target.exists(): shutil.rmtree(target)
        source=tmpbase/'episodes'/job['id']
        if source.exists(): shutil.rmtree(source)
        rec=episode(base.resolve(),job,settle)
        if job['filesystem']=='tmpfs':
            shutil.copytree(source,target); shutil.rmtree(source)
        out.write(json.dumps(rec,sort_keys=True)+'\n');out.flush()
        print(f'{i}/{len(pending)} {job["id"]} {rec["status"]}',flush=True)
    finally:
      shutil.rmtree(tmpbase,ignore_errors=True)
    summary=summarize(a.output,plan)
    print(json.dumps(summary,sort_keys=True))

if __name__=='__main__':main()
