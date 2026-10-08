"""Post-discovery, separately declared mtime-resolution diagnostic.
Runs real watchfiles + markdown-it-py + HTTP workflows. No injected events.
The same-second condition changes bytes normally; no timestamps are restored.
"""
from __future__ import annotations
import argparse,hashlib,json,shutil,time,urllib.request
from pathlib import Path

# Permit direct execution from an unpacked source tree without relying on an
# inherited PYTHONPATH.  Experiment semantics are unchanged.
import sys as _sys
from pathlib import Path as _BootstrapPath
_SRC = _BootstrapPath(__file__).resolve().parents[1] / "src"
if str(_SRC) not in _sys.path:
    _sys.path.insert(0, str(_SRC))
from watchdelta.core import create_fixture,projection,clean_build,endpoint_status
from watchdelta.replay import edit
from watchdelta.run import Worker,environment

def sleep_until(t):
    while time.time()<t:time.sleep(min(.02,max(0,t-time.time())))

def main():
    p=argparse.ArgumentParser();p.add_argument('--protocol',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    protocol=json.loads(a.protocol.read_text());a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'protocol.json').write_bytes(a.protocol.read_bytes());(a.output/'protocol.sha256').write_text(hashlib.sha256(a.protocol.read_bytes()).hexdigest()+'\n')
    (a.output/'environment.json').write_text(json.dumps(environment(),indent=2)+'\n')
    with (a.output/'records.jsonl').open('w') as out:
        for i,job in enumerate(protocol['jobs']):
            folder=(a.output/'episodes'/job['id']).resolve();folder.mkdir(parents=True);work=folder/'work';record={**job};worker=None
            try:
                # Align creation early in a wall-clock second; preserve a slipped window as a result.
                sleep_until(int(time.time())+1.03);create_fixture(work,'docs',job['mode'])
                target=work/'src/index.md';before=target.stat();worker=Worker(work,'docs',job['mode']);worker.wait('ready');metrics0=worker.stats()['metrics']
                if job['condition']=='cross_second':sleep_until(before.st_mtime_ns//1_000_000_000+1.04)
                info=edit(work,'docs','same_size',f"WD{70000+i:010d}");after=target.stat();time.sleep(protocol['settle_seconds'])
                observed=projection(work/'out','.html');metrics1=worker.stats()['metrics'];port=next(e['port'] for e in worker.events if e['kind']=='http')
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/index.html',timeout=3) as res: served=hashlib.sha256(res.read()).hexdigest()
                stderr=worker.stop();shutil.copytree(work/'out',folder/'observed');clean=clean_build(work,'docs',folder/'clean')
                record.update(status=endpoint_status(observed,clean['projection'],clean['returncode']==0),edit=info,
                  snapshot_stable=projection(folder/'observed','.html')==observed,before_mtime_ns=before.st_mtime_ns,after_mtime_ns=after.st_mtime_ns,
                  same_second=(before.st_mtime_ns//1_000_000_000==after.st_mtime_ns//1_000_000_000),mtime_changed=(before.st_mtime_ns!=after.st_mtime_ns),
                  size_unchanged=before.st_size==after.st_size,observed_projection=observed,clean=clean,
                  served_matches_disk=served==observed['index.html'],metrics={k:metrics1[k]-metrics0[k] for k in metrics1},worker_stderr=stderr)
            except Exception as e:record.update(status='infrastructure_error',error=repr(e))
            finally:
                if worker:
                    worker.stop();(folder/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in worker.events))
                (folder/'record.json').write_text(json.dumps(record,indent=2)+'\n');out.write(json.dumps(record)+'\n');out.flush()
                print(i+1,len(protocol['jobs']),job['id'],record['status'],record.get('same_second'),flush=True)
    (a.output/'complete.json').write_text(json.dumps({'episodes':len(protocol['jobs'])},indent=2)+'\n')
if __name__=='__main__':main()
