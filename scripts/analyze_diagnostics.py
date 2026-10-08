#!/usr/bin/env python3
"""Validate boundary-diagnosis and small-tree scaling records and regenerate paper inputs."""
from __future__ import annotations
import argparse, collections, hashlib, json, math, statistics
from pathlib import Path

# Permit direct execution from an unpacked source tree without relying on an
# inherited PYTHONPATH.  Experiment semantics are unchanged.
import sys as _sys
from pathlib import Path as _BootstrapPath
_SRC = _BootstrapPath(__file__).resolve().parents[1] / "src"
if str(_SRC) not in _sys.path:
    _sys.path.insert(0, str(_SRC))
from watchdelta.core import projection, source_fingerprint
from watchdelta.diagnosis import classify
ROOT=Path(__file__).resolve().parents[1]
CLASSES=['healthy','unnecessary_work','selection_failure','observation_scope_failure',
         'state_predicate_failure','scheduling_failure','consumer_failure','publication_failure']

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path:Path,text:str):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text+'\n')
def texrow(items):return ' & '.join(str(x) for x in items)+r' \\'
def med(values):return statistics.median(values) if values else None
def fmt(x,d=1):return '--' if x is None else f'{x:.{d}f}'

def validate_episode(folder:Path,r:dict)->None:
    saved=json.loads((folder/'record.json').read_text())
    if saved!=r:raise RuntimeError(f'record mismatch: {r["id"]}')
    if r['status'] not in {'matched','stale'}:raise RuntimeError(f'non-comparable episode: {r["id"]} {r["status"]}')
    ext='.js' if r['tool']=='tsc' else '.html'
    if projection(folder/'observed',ext)!=r['observed_projection']:raise RuntimeError(f'observed hash mismatch: {r["id"]}')
    if projection(folder/'clean/out',ext)!=r['clean']['projection']:raise RuntimeError(f'clean hash mismatch: {r["id"]}')
    if source_fingerprint(folder/'work',r['tool'])[0]!=r['clean']['source_sha256']:raise RuntimeError(f'work source mismatch: {r["id"]}')
    if source_fingerprint(folder/'clean',r['tool'])[0]!=r['clean']['source_sha256']:raise RuntimeError(f'clean source mismatch: {r["id"]}')
    expected='matched' if r['observed_projection']==r['clean']['projection'] else 'stale'
    if r['status']!=expected:raise RuntimeError(f'classification mismatch: {r["id"]}')
    if r['clean']['returncode']!=0:raise RuntimeError(f'oracle failed: {r["id"]}')
    if r.get('snapshot_stable') is not True:raise RuntimeError(f'endpoint snapshot unstable: {r["id"]}')
    if r['tool']=='docs' and r.get('served_matches_disk') is not True:raise RuntimeError(f'served/disk mismatch: {r["id"]}')
    if r.get('unpublished_projection') is not None:
        unpublished=projection(folder/'work/.wd-unpublished/out','.html')
        if unpublished!=r['unpublished_projection']:raise RuntimeError(f'unpublished hash mismatch: {r["id"]}')
        if r['unpublished_matches_clean']!=(unpublished==r['clean']['projection']):raise RuntimeError(f'unpublished comparison mismatch: {r["id"]}')

def validate_diagnosis(results:Path):
    folder=results/'boundary-diagnosis';protocol=json.loads((folder/'protocol.json').read_text())
    if sha(folder/'protocol.json')!=(folder/'protocol.sha256').read_text().strip():raise RuntimeError('diagnosis protocol hash')
    units=[json.loads(x) for x in (folder/'records.jsonl').read_text().splitlines() if x.strip()]
    complete=json.loads((folder/'complete.json').read_text())
    if len(units)!=48 or complete.get('units')!=48 or complete.get('executions')!=84 or not complete.get('completed_utc'):
        raise RuntimeError('diagnosis completion')
    if (ROOT/'protocols/boundary-diagnosis.json').read_bytes()!=(folder/'protocol.json').read_bytes():
        raise RuntimeError('diagnosis frozen protocol mirror differs')
    planned={u['id']:u for u in protocol['units']}
    if collections.Counter(planned.keys())!=collections.Counter(u['id'] for u in units):raise RuntimeError('diagnosis plan/record mismatch')
    executions=0
    for unit in units:
        plan=planned[unit['id']]; records={}
        if unit['truth']!=plan['truth']:raise RuntimeError('diagnosis truth changed')
        for role,spec in plan['roles'].items():
            r=json.loads((folder/'episodes'/spec['id']/'record.json').read_text());records[role]=r;executions+=1
            for k,v in spec.items():
                if r.get(k)!=v:raise RuntimeError(f'diagnosis execution attribute changed: {spec["id"]} {k}')
            validate_episode(folder/'episodes'/spec['id'],r)
        predicted,reasons=classify(records['base'],{k:v for k,v in records.items() if k!='base'})
        if predicted!=unit['predicted'] or reasons!=unit['reasons'] or unit['correct']!=(predicted==unit['truth']):raise RuntimeError(f'diagnosis recomputation: {unit["id"]}')
    if executions!=84 or not all(u['correct'] for u in units):raise RuntimeError('diagnosis accuracy/completeness')
    summary=json.loads((folder/'summary.json').read_text())
    if summary['units']!=48 or summary['executions']!=84 or summary['correct']!=48 or summary['unresolved']!=0:raise RuntimeError('diagnosis summary')
    return units,summary

def validate_scaling(results:Path):
    folder=results/'scaling-small';protocol=json.loads((folder/'protocol.json').read_text())
    if sha(folder/'protocol.json')!=(folder/'protocol.sha256').read_text().strip():raise RuntimeError('scaling protocol hash')
    records=[json.loads(x) for x in (folder/'records.jsonl').read_text().splitlines() if x.strip()]
    if (ROOT/'protocols/scaling-small.json').read_bytes()!=(folder/'protocol.json').read_bytes():
        raise RuntimeError('scaling frozen protocol mirror differs')
    planned={j['id']:j for j in protocol['jobs']}
    if len(records)!=48 or collections.Counter(planned.keys())!=collections.Counter(r['id'] for r in records):raise RuntimeError('scaling plan/record mismatch')
    env=json.loads((folder/'environment.json').read_text())
    if env['mounts']['overlay']['fstype']!='overlay' or env['mounts']['tmpfs']['fstype']!='tmpfs':raise RuntimeError('filesystem provenance')
    for r in records:
        for k,v in planned[r['id']].items():
            if r.get(k)!=v:raise RuntimeError(f'scaling attribute changed: {r["id"]} {k}')
        validate_episode(folder/'episodes'/r['id'],r)
        if r['status']!='matched':raise RuntimeError(f'scaling mismatch: {r["id"]}')
        if len(list((folder/'episodes'/r['id']/'work/src').rglob('*.ts' if r['tool']=='tsc' else '*.md')))!=r['file_count']:raise RuntimeError(f'file count mismatch: {r["id"]}')
    return records,json.loads((folder/'summary.json').read_text())

def main()->None:
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,default=ROOT/'results');p.add_argument('--paper',type=Path,required=True);a=p.parse_args()
    units,ds=validate_diagnosis(a.results);scaling,ss=validate_scaling(a.results)
    labels={'healthy':'Healthy','unnecessary_work':'Unnecessary work','selection_failure':'Selection','observation_scope_failure':'Observation scope','state_predicate_failure':'State predicate','scheduling_failure':'Scheduling','consumer_failure':'Consumer','publication_failure':'Publication'}
    signatures={'healthy':'Reference equality','unnecessary_work':'Neutral rebuild; filter removes it','selection_failure':'Broader filter repairs','observation_scope_failure':'Broader filter fails; scope repairs','state_predicate_failure':'Native + content scan repair','scheduling_failure':'Accepted; no completion','consumer_failure':'Failed completion','publication_failure':'Unpublished tree equals reference'}
    drows=[]
    for c in CLASSES:
        rs=[u for u in units if u['truth']==c]
        drows.append(texrow([labels[c],len(rs),sum(u['correct'] for u in rs),signatures[c]]))
    write(a.paper/'generated/boundary-diagnosis.tex',r'''\begin{table*}[t]
\centering
\caption{Controlled boundary-diagnosis study. A diagnostic unit may execute multiple interventions; the 48 units require 84 fresh-process episodes. Labels are ground-truth mutations, not naturally observed prevalence.}
\label{tab:boundary-diagnosis}
\begin{tabular}{lrrp{0.48\textwidth}}\toprule
Boundary class & Units & Correct & Decisive observable intervention signature\\\midrule
'''+ '\n'.join(drows)+r'''
\bottomrule\end{tabular}
\end{table*}''')
    srows=[]
    for tool,mode in [('tsc','default'),('tsc','hash'),('docs','relevant'),('docs','hash')]:
        cells=[]
        matched=total=0
        for n in [10,250]:
            rs=[r for r in scaling if r['tool']==tool and r['mode']==mode and r['file_count']==n]
            lat=[r['stable_latency_ms'] for r in rs if r.get('stable_latency_ms') is not None]
            cpu=[r['metrics']['cpu_s']*1000 for r in rs]
            scan=[r['metrics']['scan_bytes']/1024 for r in rs]
            matched+=sum(r['status']=='matched' for r in rs);total+=len(rs)
            cells.append((fmt(med(lat)),fmt(med(cpu)),fmt(med(scan))))
        srows.append(texrow([tool,mode,f"{matched}/{total}",f"{cells[0][0]} $\\rightarrow$ {cells[1][0]}",f"{cells[0][1]} $\\rightarrow$ {cells[1][1]}",f"{cells[0][2]} $\\rightarrow$ {cells[1][2]}"]))
    write(a.paper/'generated/scaling-small.tex',r'''\begin{table*}[t]
\centering
\caption{Tree-size holdout, with medians shown as 10 $\rightarrow$ 250 files. Each endpoint pools three overlay and three tmpfs repetitions. CPU and scanned KiB cover the bounded post-readiness episode, not startup.}
\label{tab:scaling-small}
\begin{tabular}{llrrrr}\toprule
Path & Mode & Match & Latency ms & CPU ms & Scanned KiB\\\midrule
'''+ '\n'.join(srows)+r'''
\bottomrule\end{tabular}
\end{table*}''')
    base=json.loads((a.results/'derived/extensions-summary.json').read_text())
    runtime=base['runtime_total']['n']+ds['executions']+ss['episodes']
    all_cases=runtime+base['vite']['cases']+base['mkdocs']['episodes']
    macros={'DiagnosisUnitN':ds['units'],'DiagnosisExecutionN':ds['executions'],'DiagnosisCorrectN':ds['correct'],
            'DiagnosisUnresolvedN':ds['unresolved'],'ScalingN':ss['episodes'],'ScalingMatchedN':ss['matched'],
            'DiagnosticsRuntimeEpisodeN':runtime,'DiagnosticsAllEvidenceN':all_cases}
    write(a.paper/'generated/numbers-diagnostics.tex','% Generated from validated boundary-diagnosis and small-tree scaling records.\n'+'\n'.join('\\newcommand{\\'+k+'}{'+str(v)+'}' for k,v in macros.items()))
    write(a.paper/'generated/evidence.tex',r'''\begin{table*}[t]
\centering
\caption{Executed evidence layers. Counts are not pooled into a failure-rate estimate because ordinary edits, stress cases, controlled mutations, and source-level replays answer different questions.}
\label{tab:evidence}
\begin{tabular}{p{0.16\textwidth}p{0.28\textwidth}rp{0.36\textwidth}}\toprule
Layer & Systems and protocols & Executions & What is checked\\\midrule
Primary runtime matrix & TypeScript watch; watchfiles/Markdown/HTTP & 432 & Nine configurations, eight edit patterns, six repetitions; final output versus isolated execution.\\
Runtime diagnostics & Timing, baseline/deadline, Uvicorn, long budget, sensitivity, Hypercorn & 114 & Mechanism controls and independent CLI integrations; deliberate faults remain labeled.\\
Boundary diagnosis & Eight ground-truth classes, six units each & 84 & Forty-eight classification units using explicit repair interventions; 48/48 classified, zero unresolved.\\
Tree-size/filesystem holdout & 10/250 files; overlay/tmpfs; native/content modes & 48 & Final consistency and post-readiness latency, CPU, and scan work.\\
Versioned mechanism replays & Vite tagged decisions; merged MkDocs build loop & 72 & Exact declared source boundary, not full application runtime.\\
\bottomrule\end{tabular}
\end{table*}''')
    summary={'diagnosis':ds,'scaling':ss,'runtime_total':runtime,'all_executed_cases':all_cases}
    write(a.results/'derived/diagnostics-summary.json',json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
