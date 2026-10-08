#!/usr/bin/env python3
"""Validate the added Hypercorn holdout and versioned historical mechanism replays."""
from __future__ import annotations
import argparse, collections, hashlib, json, statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def texrow(items):return ' & '.join(str(x) for x in items)+r' \\'
def write(path:Path,text:str):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text+'\n')
def median(values):return statistics.median(values) if values else None

def validate_hypercorn(results:Path):
    folder=results/'hypercorn-integration';protocol=json.loads((folder/'protocol.json').read_text())
    if sha(folder/'protocol.json')!=(folder/'protocol.sha256').read_text().strip():raise RuntimeError('Hypercorn protocol hash mismatch')
    records=[json.loads(x) for x in (folder/'records.jsonl').read_text().splitlines() if x.strip()]
    if json.loads((folder/'complete.json').read_text()).get('episodes')!=len(protocol['jobs']):raise RuntimeError('Hypercorn incomplete')
    if collections.Counter(r['id'] for r in records)!=collections.Counter(j['id'] for j in protocol['jobs']):raise RuntimeError('Hypercorn plan/record mismatch')
    jobs={j['id']:j for j in protocol['jobs']}
    for r in records:
        if any(r.get(k)!=v for k,v in jobs[r['id']].items()):raise RuntimeError(f'Hypercorn attributes changed: {r["id"]}')
        case=folder/'episodes'/r['id']
        if json.loads((case/'record.json').read_text())!=r:raise RuntimeError(f'Hypercorn record mismatch: {r["id"]}')
        if sha(case/'final-app.py')!=r['source_sha256']:raise RuntimeError(f'Hypercorn source mismatch: {r["id"]}')
        if r['oracle']['returncode']!=0 or r['expected'] is None:raise RuntimeError(f'Hypercorn oracle failed: {r["id"]}')
        expected_status='matched' if r['observed']==r['expected'] else 'stale'
        if r['status']!=expected_status:raise RuntimeError(f'Hypercorn misclassified: {r["id"]}')
        if r['scenario']=='preserved_stat':
            if r['status']!='stale' or r['reload_imports']!=0 or not r['edit']['mtime_restored']:raise RuntimeError(f'Hypercorn stress invariant: {r["id"]}')
        elif r['scenario']=='temporary':
            if r['status']!='matched' or r['reload_imports']!=0 or r['edit']['obligation']:raise RuntimeError(f'Hypercorn control invariant: {r["id"]}')
        elif r['status']!='matched' or r['reload_imports']<1:raise RuntimeError(f'Hypercorn ordinary invariant: {r["id"]}')
    return records,protocol

def validate_vite(results:Path):
    folder=results/'vite-filter-replay';summary=json.loads((folder/'summary.json').read_text())
    records=[json.loads(x) for x in (folder/'records.jsonl').read_text().splitlines() if x.strip()]
    if len(records)!=summary['cases'] or len(records)!=48:raise RuntimeError('Vite replay count')
    old=ROOT/'evidence/upstream/vite/watch-v5.2.4.ts';fixed=ROOT/'evidence/upstream/vite/watch-v5.2.10.ts'
    if sha(old)!=summary['source']['old']['sha256'] or sha(fixed)!=summary['source']['fixed']['sha256']:raise RuntimeError('Vite source hash mismatch')
    issue=next(r for r in records if r['case']=='issue-empty-false/configured-outdir')
    if not issue['oldIgnored'] or issue['fixedIgnored']:raise RuntimeError('Vite issue boundary missing')
    if sum(r['changed'] for r in records)!=summary['changed']:raise RuntimeError('Vite summary mismatch')
    return records,summary

def validate_mkdocs(results:Path):
    folder=results/'mkdocs-batch-replay';summary=json.loads((folder/'summary.json').read_text())
    records=[json.loads(x) for x in (folder/'records.jsonl').read_text().splitlines() if x.strip()]
    source=ROOT/'evidence/upstream/mkdocs/livereload-a444c434.py'
    if sha(source)!=summary['source_sha256']:raise RuntimeError('MkDocs source hash mismatch')
    if len(records)!=24 or not all(r['matched_expectation'] for r in records):raise RuntimeError('MkDocs replay failed')
    if summary['burst_events']!=360 or summary['burst_builds']!=9:raise RuntimeError('MkDocs burst summary mismatch')
    return records,summary

def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,default=ROOT/'results');p.add_argument('--paper',type=Path,required=True);a=p.parse_args()
    h,hp=validate_hypercorn(a.results);v,vs=validate_vite(a.results);m,ms=validate_mkdocs(a.results)
    base=json.loads((a.results/'derived/summary.json').read_text())
    base_n=sum(x['n'] for x in base['datasets'].values());base_matched=sum(x['outcomes'].get('matched',0) for x in base['datasets'].values());base_stale=sum(x['outcomes'].get('stale',0) for x in base['datasets'].values())
    hrows=[]
    for scenario in ['same_size','inplace','atomic','burst','preserved_stat','temporary']:
        rs=[r for r in h if r['scenario']==scenario];lat=[r['response_latency_ms'] for r in rs if r.get('response_latency_ms') is not None]
        hrows.append(texrow([scenario.replace('_',' '),f"{sum(r['status']=='matched' for r in rs)}/{len(rs)}",sum(r['reload_imports'] for r in rs),'--' if not lat else f'{median(lat):.1f}']))
    write(a.paper/'generated/hypercorn.tex',r'''\begin{table}[t]
\centering
\caption{Fresh-process Hypercorn 0.18.0 reload holdout. The endpoint is 2.35 seconds after the edit. Latency is first sampled expected response and is undefined for controls and stale cases.}
\label{tab:hypercorn}
\begin{tabular}{lrrr}\toprule
Edit & Match & Reloads & Median ms\\\midrule
'''+ '\n'.join(hrows)+r'''
\bottomrule\end{tabular}
\end{table}''')
    write(a.paper/'generated/history.tex',r'''\begin{table*}[t]
\centering
\caption{Versioned historical mechanism checks. These rows do not claim full application-runtime reproduction; each row states the executed boundary.}
\label{tab:history}
\begin{tabular}{p{0.16\textwidth}p{0.23\textwidth}rp{0.43\textwidth}}\toprule
System & Executed boundary & Cases & Result\\\midrule
Vite 5.2.4/5.2.10 & Exact out-directory decision on simple absolute paths & 48 & 14 decisions changed. In the reported \texttt{emptyOutDir=false} case, the source path changed from ignored to watched.\\
MkDocs PR 2385 & Exact merged \texttt{\_build\_loop}, callbacks injected after observer acceptance & 24 & All expected invariants held; 360 rapid callbacks produced nine builds, while spaced callbacks and events during a build were retained.\\
\bottomrule\end{tabular}
\end{table*}''')
    uv=base['datasets']['uvicorn-integration']
    # The compact paper integration table is regenerated here from both actual-process integrations.
    uv_records=[json.loads(x) for x in (a.results/'uvicorn-integration'/'records.jsonl').read_text().splitlines() if x.strip()]
    integration_rows=[]
    for mode,scenario,system_label,edit_label in [
        ('default','same_size','Uvicorn default','Markdown same size'),
        ('include_md','same_size','Uvicorn include md','Markdown same size'),
        ('include_md','atomic','Uvicorn include md','Markdown atomic'),
        ('include_md','temporary','Uvicorn include md','Temporary'),
    ]:
        rs=[r for r in uv_records if r['mode']==mode and r['scenario']==scenario]
        integration_rows.append(texrow([system_label,edit_label,f"{sum(r['status']=='matched' for r in rs)}/{len(rs)}",sum(r.get('rerenders',0) for r in rs)]))
    for scenario,edit_label in [('same_size','Python same size'),('inplace','Python in place'),('atomic','Python atomic'),('burst','Python burst'),('preserved_stat','Preserved stat'),('temporary','Temporary')]:
        rs=[r for r in h if r['scenario']==scenario]
        integration_rows.append(texrow(['Hypercorn default',edit_label,f"{sum(r['status']=='matched' for r in rs)}/{len(rs)}",sum(r.get('reload_imports',0) for r in rs)]))
    write(a.paper/'generated/integrations.tex',r'''\begin{table}[t]
\centering
\caption{Independent reload integrations. Each cell uses a fresh process. ``Reloads'' is the total over repetitions; controls have no output change obligation.}
\label{tab:integrations}
\begin{tabular}{llrr}
\toprule
System/selection & Edit & Match & Reloads\\
\midrule
'''+ '\n'.join(integration_rows)+r'''
\bottomrule
\end{tabular}
\end{table}''')
    write(a.paper/'generated/evidence.tex',r'''\begin{table*}[t]
\centering
\caption{Executed evidence layers. Counts are not pooled into a failure-rate estimate because the layers include ordinary edits, stress strata, injected faults, configuration controls, and source-level replays.}
\label{tab:evidence}
\begin{tabular}{p{0.18\textwidth}p{0.29\textwidth}rp{0.40\textwidth}}
\toprule
Layer & Systems and protocols & Cases & What is actually checked\\
\midrule
Primary runtime matrix & TypeScript 5.8.3 watch; watchfiles 1.2.0 + markdown-it-py 4.2.0 server & 432 & Fresh process, bounded edit, generated bytes, executable/HTTP consumer, and isolated one-shot reference.\\
Runtime diagnostics & Timing 30; baseline/deadline 18; Uvicorn 12; long-budget 12; fault/filter sensitivity 18; Hypercorn 24 & 114 & Mechanism-specific controls and independent CLI integrations; injected cases are labeled and excluded from natural-failure interpretations.\\
Versioned replays & Vite 5.2.4/5.2.10 decision logic; merged MkDocs PR 2385 build loop & 72 & Exact source decisions or merged scheduling mechanism at a declared boundary, not full application-runtime reproduction.\\
\bottomrule
\end{tabular}
\end{table*}''')
    runtime_n=base_n+len(h);runtime_matched=base_matched+sum(r['status']=='matched' for r in h);runtime_stale=base_stale+sum(r['status']=='stale' for r in h)
    all_evidence=runtime_n+len(v)+len(m)
    macros={'RuntimeEpisodeN':runtime_n,'RuntimeMatchedN':runtime_matched,'RuntimeStaleN':runtime_stale,
      'HypercornN':len(h),'HypercornMatched':sum(r['status']=='matched' for r in h),'HypercornPreservedStale':sum(r['status']=='stale' for r in h if r['scenario']=='preserved_stat'),
      'ViteReplayN':len(v),'ViteChangedN':vs['changed'],'MkDocsReplayN':len(m),'MkDocsBurstEvents':ms['burst_events'],'MkDocsBurstBuilds':ms['burst_builds'],'AllEvidenceN':all_evidence}
    write(a.paper/'generated/numbers-integrations.tex','% Generated from separately validated extension records.\n'+'\n'.join('\\newcommand{\\'+k+'}{'+str(val)+'}' for k,val in macros.items()))
    summary={'hypercorn':{'n':len(h),'outcomes':dict(collections.Counter(r['status'] for r in h)),'protocol':hp['id']},
      'vite':vs,'mkdocs':ms,'base_runtime':{'n':base_n,'matched':base_matched,'stale':base_stale},
      'runtime_total':{'n':runtime_n,'matched':runtime_matched,'stale':runtime_stale},'all_executed_cases':all_evidence,
      'excluded_pilot':'results/pilots/hypercorn-oracle-contamination'}
    write(a.results/'derived/extensions-summary.json',json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
