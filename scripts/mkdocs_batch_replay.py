"""Execute the exact merged MkDocs PR #2385 build loop with controlled callbacks.

The source snapshot is executed unchanged. Small watchdog stubs satisfy imports;
the server is allocated without its network/observer constructor, and accepted
callbacks are inserted at the exact queue boundary used by ``watch``. This is a
source-mechanism replay, not a full MkDocs runtime reproduction.
"""
from __future__ import annotations
import argparse, hashlib, json, sys, threading, time, types
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'evidence/upstream/mkdocs/livereload-a444c434.py'

def load_class():
    watchdog=types.ModuleType('watchdog');events=types.ModuleType('watchdog.events');observers=types.ModuleType('watchdog.observers')
    class FileModifiedEvent: pass
    class FileSystemEventHandler: pass
    class Observer: pass
    events.FileModifiedEvent=FileModifiedEvent;events.FileSystemEventHandler=FileSystemEventHandler;observers.Observer=Observer
    watchdog.events=events;watchdog.observers=observers
    saved={k:sys.modules.get(k) for k in ('watchdog','watchdog.events','watchdog.observers')}
    sys.modules['watchdog']=watchdog;sys.modules['watchdog.events']=events;sys.modules['watchdog.observers']=observers
    try:
        namespace={'__file__':str(SOURCE),'__name__':'watchdelta_mkdocs_2385'}
        text=SOURCE.read_text();exec(compile(text,str(SOURCE),'exec'),namespace)
        return namespace['LiveReloadServer'],text
    finally:
        for k,v in saved.items():
            if v is None:sys.modules.pop(k,None)
            else:sys.modules[k]=v

def one_case(cls,case):
    calls=[];server=object.__new__(cls)
    server.build_delay=case['build_delay'];server.shutdown_delay=.02
    server._wanted_epoch=0;server._visible_epoch=0;server._epoch_cond=threading.Condition()
    server._to_rebuild={};server._rebuild_cond=threading.Condition();server._shutdown=False
    build_started=threading.Event()
    def make_builder(name,sleep=0):
        def builder():
            calls.append({'name':name,'start_ns':time.monotonic_ns()});build_started.set()
            if sleep:time.sleep(sleep)
            calls[-1]['end_ns']=time.monotonic_ns()
        return builder
    builders=[make_builder(f'b{i}',case.get('builder_sleep',0)) for i in range(case['functions'])]
    thread=threading.Thread(target=server._build_loop);thread.start();start=time.monotonic_ns()
    for i in range(case['events']):
        func=builders[i%len(builders)]
        with server._rebuild_cond:
            server._to_rebuild[func]=True;server._rebuild_cond.notify_all()
        if case.get('during_build') and i==0:
            if not build_started.wait(2):raise RuntimeError('builder did not start')
        if i+1<case['events'] and case['gap']:
            time.sleep(case['gap'])
    # allow final quiet period and any second batch to finish
    time.sleep(case['build_delay']+case.get('builder_sleep',0)+.20)
    with server._rebuild_cond:
        server._shutdown=True;server._rebuild_cond.notify_all()
    thread.join(3)
    if thread.is_alive():raise RuntimeError('build loop did not stop')
    return {**case,'calls':calls,'builds':len(calls),'elapsed_ms':(time.monotonic_ns()-start)/1e6,
            'matched_expectation':len(calls)==case['expected_builds']}

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise SystemExit('Refusing to overwrite output')
    a.output.mkdir(parents=True);cls,text=load_class()
    templates=[
      {'id':'single','events':1,'gap':0,'functions':1,'build_delay':.25,'expected_builds':1},
      {'id':'burst10','events':10,'gap':0,'functions':1,'build_delay':.25,'expected_builds':1},
      {'id':'burst100','events':100,'gap':0,'functions':1,'build_delay':.25,'expected_builds':1},
      {'id':'stream10-50ms','events':10,'gap':.05,'functions':1,'build_delay':.25,'expected_builds':1},
      {'id':'two-functions-burst','events':20,'gap':0,'functions':2,'build_delay':.25,'expected_builds':2},
      {'id':'spaced4','events':4,'gap':.35,'functions':1,'build_delay':.25,'expected_builds':4},
      {'id':'spaced4-two-functions','events':4,'gap':.35,'functions':2,'build_delay':.25,'expected_builds':4},
      {'id':'event-during-build','events':2,'gap':0,'functions':1,'build_delay':.10,'builder_sleep':.25,'during_build':True,'expected_builds':2},
    ]
    records=[]
    for rep in range(3):
        for template in templates:
            case={**template,'replicate':rep,'case':f"{template['id']}-r{rep}"}
            record=one_case(cls,case);records.append(record);print(record['case'],record['builds'],record['matched_expectation'],flush=True)
    (a.output/'records.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
    summary={'classification':'exact merged MkDocs _build_loop replay at accepted-callback boundary; not full MkDocs runtime',
      'episodes':len(records),'all_expected':all(r['matched_expectation'] for r in records),
      'source_sha256':hashlib.sha256(text.encode()).hexdigest(),
      'burst_events':sum(r['events'] for r in records if r['id'].startswith('burst') or r['id'].startswith('stream')),
      'burst_builds':sum(r['builds'] for r in records if r['id'].startswith('burst') or r['id'].startswith('stream'))}
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
