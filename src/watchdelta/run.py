from __future__ import annotations
import argparse,hashlib,importlib.metadata,json,os,platform,shutil,signal,subprocess,sys,threading,time,urllib.request
from pathlib import Path
from typing import Any
from .core import create_fixture,projection,clean_build,endpoint_status,stable_latency,tsc_path,tsc_command,build_once,module_subprocess_env
from .replay import edit
ROOT=Path(__file__).resolve().parents[2]

class Worker:
    def __init__(self,root:Path,tool:str,mode:str,inject:str='none'):
        self.events:list[dict[str,Any]]=[]; self.condition=threading.Condition()
        self.p=subprocess.Popen([sys.executable,'-u','-m','watchdelta.worker','--root',str(root),
            '--tool',tool,'--mode',mode,'--inject',inject],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,text=True,bufsize=1,start_new_session=True,env=module_subprocess_env())
        threading.Thread(target=self._reader,daemon=True).start()
    def _reader(self)->None:
        assert self.p.stdout
        for line in self.p.stdout:
            try: event=json.loads(line)
            except ValueError: event={'kind':'nonjson','text':line,'t_ns':time.monotonic_ns()}
            with self.condition: self.events.append(event); self.condition.notify_all()
    def wait(self,kind:str,since:int=0,timeout:float=30)->dict:
        limit=time.monotonic()+timeout
        with self.condition:
            while True:
                for e in self.events[since:]:
                    if e['kind']==kind:return e
                if self.p.poll() is not None: raise RuntimeError(f'Worker exited {self.p.returncode}: {self.events[-5:]}')
                if time.monotonic()>limit: raise TimeoutError(f'No {kind}: {self.events[-5:]}')
                self.condition.wait(.05)
    def stats(self)->dict:
        n=len(self.events); assert self.p.stdin; self.p.stdin.write('stats\n'); self.p.stdin.flush()
        return self.wait('stats',n,timeout=10)
    def stop(self)->str:
        if self.p.poll() is None:
            os.killpg(self.p.pid,signal.SIGTERM)
            try:self.p.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(self.p.pid,signal.SIGKILL);self.p.wait()
        return self.p.stderr.read() if self.p.stderr else ''

def completed_builds(events: list[dict[str, Any]], start_ns: int, end_ns: int) -> int:
    """Count successful end records, not starts or nonfailed attempts.

    The measurement interval excludes startup and includes its ending snapshot.
    Missing or failed completion records never establish completion.
    """
    if end_ns < start_ns:
        raise ValueError('Completion window ends before it starts')
    return sum(e.get('kind') == 'build_end' and e.get('returncode') == 0
               and start_ns < e.get('t_ns', -1) <= end_ns for e in events)

def environment()->dict:
    return {'python':sys.version,'node':subprocess.check_output(['node','--version'],text=True).strip(),
       'typescript':subprocess.check_output([*tsc_command(),'--version'],text=True).strip(),
       'packages':{k:importlib.metadata.version(k) for k in ['watchfiles','markdown-it-py','mdurl']},
       'platform':platform.platform(),'machine':platform.machine(),'cpus':os.cpu_count(),
       'filesystem':subprocess.check_output(['findmnt','-T',str(ROOT),'-n','-o','FSTYPE'],text=True).strip(),
       'clock':'CLOCK_MONOTONIC (nanoseconds)','cwd_placeholder':'<artifact>',
       'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}

def episode(base:Path,case:dict,settle:float)->dict:
    folder=base/'episodes'/case['id']; folder.mkdir(parents=True)
    work=folder/'work';create_fixture(work,case['tool'],case['mode'],case.get('file_count'))
    ext='.js' if case['tool']=='tsc' else '.html'
    worker=Worker(work,case['tool'],case['mode'],case.get('inject','none'))
    record:dict={**case,'status':'infrastructure_error'}; timeline=[]; stopped=False
    try:
        ready=worker.wait('ready',timeout=35); initial=projection(work/'out',ext)
        if not initial:raise RuntimeError('Readiness announced without output')
        start_snapshot=worker.stats(); start_metrics=start_snapshot['metrics']; capture_stop=threading.Event()
        def capture()->None:
            while not capture_stop.is_set():
                t=time.monotonic_ns(); timeline.append({'t_ns':t,'projection':projection(work/'out',ext)})
                capture_stop.wait(.02)
        sampler=threading.Thread(target=capture,daemon=True);sampler.start()
        edit_info=edit(work,case['tool'],case['scenario'],f"WD{case['numeric_id']:010d}")
        deadline=edit_info['end_ns']/1e9+settle
        while time.monotonic()<deadline:time.sleep(min(.02,max(0,deadline-time.monotonic())))
        capture_stop.set();sampler.join(timeout=3); observed=projection(work/'out',ext)
        timeline.append({'t_ns':time.monotonic_ns(),'projection':observed}); served={}
        # Close the measurement interval before diagnostic HTTP probes; otherwise
        # serving every page is charged to the watcher/renderer at large scale.
        end_snapshot=worker.stats(); end_metrics=end_snapshot['metrics']; observation_ns=timeline[-1]['t_ns']
        if case['tool']=='docs':
            port=next(e['port'] for e in worker.events if e['kind']=='http')
            for rel in observed:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/{rel}',timeout=3) as response:
                    served[rel]=hashlib.sha256(response.read()).hexdigest()
        stderr=worker.stop();stopped=True; shutil.copytree(work/'out',folder/'observed')
        snapshot_stable=projection(folder/'observed',ext)==observed
        clean=clean_build(work,case['tool'],folder/'clean')
        status=endpoint_status(observed,clean['projection'],clean['returncode']==0)
        latency=stable_latency(timeline,clean['projection'],edit_info['end_ns'],edit_info['obligation'])
        metrics={k:end_metrics[k]-start_metrics[k] for k in end_metrics}; builds=metrics['builds']; failures=metrics['failed_builds']
        semantic=None; clean_semantic=None
        if case['tool']=='tsc':
            def execute(directory:Path)->dict:
                result=subprocess.run(['node',str(directory/'out/index.js')],capture_output=True,text=True,timeout=5)
                return {'returncode':result.returncode,'stdout':result.stdout.strip(),'stderr':result.stderr.strip()}
            semantic=execute(work);clean_semantic=execute(folder/'clean')
        record.update(status=status,snapshot_stable=snapshot_stable,obligation_consistent=(initial!=clean['projection'])==edit_info['obligation'],edit=edit_info,ready_ns=ready['t_ns'],initial_projection=initial,
             observed_projection=observed,clean=clean,served_projection=served,
             served_matches_disk=(served==observed if case['tool']=='docs' else None),runtime=semantic,clean_runtime=clean_semantic,
             runtime_matches=(semantic==clean_semantic if case['tool']=='tsc' else None),
             stable_latency_ms=latency,metrics=metrics,observation_ms=(observation_ns-edit_info['end_ns'])/1e6,
             nominal_budget_ms=settle*1000, metrics_include_http_probes=False,
             noise_rebuilds=(builds if not edit_info['obligation'] else 0),
             additional_builds=max(0,builds-int(edit_info['obligation'])),
             completed_builds=completed_builds(worker.events,start_snapshot['t_ns'],end_snapshot['t_ns']),
             completion_window_ns=[start_snapshot['t_ns'],end_snapshot['t_ns']],
             completion_observed=completed_builds(worker.events,start_snapshot['t_ns'],end_snapshot['t_ns'])>0,
             unpublished_projection=next((e.get('unpublished_projection') for e in reversed(worker.events) if e.get('kind')=='build_end' and e.get('published') is False),None),
             worker_stderr=stderr)
        record['unpublished_matches_clean']=(record['unpublished_projection']==clean['projection'] if record.get('unpublished_projection') is not None else None)
        if status=='stale' and case.get('diagnostic',False):
            build_once(work,case['tool'])
            record['manual_rebuild_matches']=projection(work/'out',ext)==clean['projection']
            shutil.copytree(work/'out',folder/'manual_rebuild')
    except Exception as exc: record.update(error=repr(exc))
    finally:
        if not stopped:record['worker_stderr']=worker.stop()
        (folder/'record.json').write_text(json.dumps(record,indent=2)+'\n')
        (folder/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in worker.events))
        (folder/'timeline.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in timeline))
    return record

def main()->None:
    p=argparse.ArgumentParser();p.add_argument('--protocol',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int);a=p.parse_args()
    data=a.protocol.read_bytes();protocol=json.loads(data)
    if a.output.exists():raise SystemExit('Refusing to overwrite a result directory')
    a.output.mkdir(parents=True)
    (a.output/'environment.json').write_text(json.dumps(environment(),indent=2)+'\n')
    (a.output/'protocol.json').write_bytes(data);(a.output/'protocol.sha256').write_text(hashlib.sha256(data).hexdigest()+'\n')
    jobs=protocol['jobs'][:a.limit] if a.limit else protocol['jobs']
    with (a.output/'records.jsonl').open('w') as f:
        for i,job in enumerate(jobs):
            r=episode(a.output.resolve(),job,protocol['settle_seconds']);f.write(json.dumps(r)+'\n');f.flush()
            print(f"{i+1}/{len(jobs)} {job['id']} {r['status']} latency={r.get('stable_latency_ms')}",flush=True)
    (a.output/'complete.json').write_text(json.dumps({'episodes':len(jobs),'completed_utc':
        time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())},indent=2)+'\n')
if __name__=='__main__':main()
