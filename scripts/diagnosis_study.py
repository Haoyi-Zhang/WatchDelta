#!/usr/bin/env python3
"""Execute a frozen, mutation-based boundary-diagnosis study.

Each diagnostic unit has a known injected boundary and one or more explicit
interventions. The unit, not each intervention run, is the classification
sample. All executions use the same real TypeScript or watchfiles/Markdown
process adapters used by the primary study.
"""
from __future__ import annotations
import argparse, hashlib, json, shutil, time
from pathlib import Path

# Permit direct execution from an unpacked source tree without relying on an
# inherited PYTHONPATH.  Experiment semantics are unchanged.
import sys as _sys
from pathlib import Path as _BootstrapPath
_SRC = _BootstrapPath(__file__).resolve().parents[1] / "src"
if str(_SRC) not in _sys.path:
    _sys.path.insert(0, str(_SRC))
from watchdelta.diagnosis import classify
from watchdelta.run import episode, environment

CLASSES = [
    'healthy', 'unnecessary_work', 'selection_failure',
    'observation_scope_failure', 'state_predicate_failure',
    'scheduling_failure', 'consumer_failure', 'publication_failure'
]

def case(case_id: str, numeric: int, tool: str, mode: str, scenario: str,
         inject: str='none', diagnostic: bool=True) -> dict:
    return {'id':case_id,'numeric_id':numeric,'tool':tool,'mode':mode,
            'scenario':scenario,'inject':inject,'diagnostic':diagnostic}

def frozen_units(repetitions: int=6) -> list[dict]:
    units=[]; numeric=800000
    for rep in range(1,repetitions+1):
        tool='docs' if rep % 2 else 'tsc'
        native='relevant' if tool=='docs' else 'default'
        poll='poll'; hsh='hash'; select='wrong_filter'
        definitions=[
          ('healthy', {'base':case('',numeric,tool,native,'same_size')}),
          ('unnecessary_work', {
              'base':case('',numeric+10,'docs','default','temporary'),
              'relevance_filter':case('',numeric+11,'docs','relevant','temporary')}),
          ('selection_failure', {
              'base':case('',numeric+20,tool,select,'same_size'),
              'broad_filter':case('',numeric+21,tool,native,'same_size')}),
          ('observation_scope_failure', {
              'base':case('',numeric+30,'docs','blind','same_size'),
              'broad_filter_same_scope':case('',numeric+31,'docs','blind_default','same_size'),
              'correct_scope':case('',numeric+32,'docs','relevant','same_size')}),
          ('state_predicate_failure', {
              'base':case('',numeric+40,tool,poll,'preserved_stat'),
              'native_notification':case('',numeric+41,tool,native,'preserved_stat'),
              'content_scan':case('',numeric+42,tool,hsh,'preserved_stat')}),
          ('scheduling_failure', {
              'base':case('',numeric+50,'docs','relevant','same_size','drop')}),
          ('consumer_failure', {
              'base':case('',numeric+60,'docs','relevant','same_size','fail')}),
          ('publication_failure', {
              'base':case('',numeric+70,'docs','relevant','same_size','publish_stale')}),
        ]
        for truth,roles in definitions:
            unit_id=f'{truth}-r{rep:02d}'
            for role,spec in roles.items():
                spec['id']=f'{unit_id}--{role}'
                spec['diagnostic_truth']=truth; spec['diagnostic_role']=role
            units.append({'id':unit_id,'truth':truth,'roles':roles})
        numeric += 100
    return units

def write_summary(output: Path, units: list[dict], execution_count: int) -> dict:
    records=[json.loads(x) for x in (output/'records.jsonl').read_text().splitlines() if x.strip()]
    confusion={t:{pred:0 for pred in CLASSES+['unresolved']} for t in CLASSES}
    for r in records: confusion[r['truth']][r['predicted']]+=1
    summary={'units':len(records),'planned_units':len(units),'executions':execution_count,
             'correct':sum(r['correct'] for r in records),
             'unresolved':sum(r['predicted']=='unresolved' for r in records),
             'confusion':confusion,'completed_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    if len(records)==len(units):
        (output/'complete.json').write_text(json.dumps({'units':len(units),'executions':execution_count,
          'completed_utc':summary['completed_utc']},indent=2)+'\n')
    return summary

def main() -> None:
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--protocol',type=Path);p.add_argument('--settle',type=float)
    p.add_argument('--resume',action='store_true');p.add_argument('--max-units',type=int);a=p.parse_args()
    if a.protocol:
        raw=a.protocol.read_bytes();protocol=json.loads(raw);units=protocol['units']
        if a.settle is not None and a.settle != protocol['settle_seconds']:
            raise SystemExit('--settle disagrees with frozen protocol')
        settle=float(protocol['settle_seconds'])
    else:
        settle=1.5 if a.settle is None else a.settle;units=frozen_units()
        protocol={'id':'boundary-diagnosis','settle_seconds':settle,'repetitions':6,
                  'unit_is_sample':True,'classes':CLASSES,'units':units}
        raw=(json.dumps(protocol,indent=2,sort_keys=True)+'\n').encode()
    if a.output.exists():
        if not a.resume: raise SystemExit(f'Refusing existing output: {a.output}')
        if (a.output/'protocol.json').read_bytes()!=raw: raise SystemExit('Resume protocol differs')
    else:
        a.output.mkdir(parents=True)
        (a.output/'protocol.json').write_bytes(raw)
        (a.output/'protocol.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')
        (a.output/'environment.json').write_text(json.dumps(environment(),indent=2)+'\n')
        (a.output/'records.jsonl').write_text('')
    complete_records=[json.loads(x) for x in (a.output/'records.jsonl').read_text().splitlines() if x.strip()]
    completed={r['id'] for r in complete_records}
    execution_count=sum(len(u['roles']) for u in units if u['id'] in completed)
    pending=[u for u in units if u['id'] not in completed]
    if a.max_units is not None: pending=pending[:a.max_units]
    with (a.output/'records.jsonl').open('a') as out:
        for index,unit in enumerate(pending,1):
            records={}
            for role,spec in unit['roles'].items():
                folder=a.output/'episodes'/spec['id']
                if folder.exists(): shutil.rmtree(folder)
                rec=episode(a.output.resolve(),spec,settle)
                records[role]=rec; execution_count += 1
            predicted,reasons=classify(records['base'],{k:v for k,v in records.items() if k!='base'})
            unit_record={'id':unit['id'],'truth':unit['truth'],'predicted':predicted,
                         'correct':predicted==unit['truth'],'reasons':reasons,
                         'execution_ids':{k:v['id'] for k,v in records.items()},
                         'base_status':records['base']['status']}
            out.write(json.dumps(unit_record,sort_keys=True)+'\n');out.flush()
            print(f'{index}/{len(pending)} {unit["id"]}: {predicted}',flush=True)
    summary=write_summary(a.output,units,execution_count)
    print(json.dumps({'completed_units':summary['units'],'planned_units':summary['planned_units'],
                      'executions':summary['executions'],'correct':summary['correct']},sort_keys=True))
    if summary['correct'] != summary['units']:
        raise SystemExit(f'Diagnosis mismatches: {summary["units"]-summary["correct"]}')

if __name__=='__main__': main()
