#!/usr/bin/env python3
"""Validate recorded episodes and regenerate paper tables without third-party analysis packages.
No incomplete run is accepted, and every planned case remains in the denominator.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,math,statistics,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONFIGS=[('tsc','default','TS default'),('tsc','recommended','TS native options'),('tsc','poll','TS fixed polling'),('tsc','hash','TS content scan'),('docs','default','Docs default'),('docs','relevant','Docs relevant'),('docs','tuned','Docs tuned'),('docs','poll','Docs polling'),('docs','hash','Docs content scan')]
SCENARIOS=['inplace','atomic','burst','newdir','temporary','same_size','chunked','preserved_stat']
DATASETS=['primary-matrix','sensitivity','timing-diagnostic','baseline-challenge','uvicorn-integration','long-budget']

def manifest(folder:Path,extension:str)->dict:
    answer={}
    for path in sorted(folder.rglob('*'+extension)):
        if path.is_symlink():raise RuntimeError(f'Unexpected symlink: {path}')
        if path.is_file():answer[path.relative_to(folder).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    return answer

def source_hash(folder:Path,tool:str)->str:
    h=hashlib.sha256();ext='.ts' if tool=='tsc' else '.md'
    for path in sorted((folder/'src').rglob('*'+ext)):
        if not path.is_file() or any(x.startswith('.') for x in path.relative_to(folder/'src').parts):continue
        data=path.read_bytes();name=path.relative_to(folder).as_posix().encode()
        h.update(len(name).to_bytes(8,'big'));h.update(name);h.update(len(data).to_bytes(8,'big'));h.update(data)
    return h.hexdigest()

def load(name:str,results:Path)->list[dict]:
    folder=results/name
    if not (folder/'complete.json').exists():raise RuntimeError(f'Run is not complete: {name}')
    records=[json.loads(line) for line in (folder/'records.jsonl').read_text().splitlines()]
    plan=json.loads((folder/'protocol.json').read_text())
    planned=[r['id'] for r in plan['jobs']];actual=[r['id'] for r in records]
    if collections.Counter(planned)!=collections.Counter(actual):raise RuntimeError(f'Planned/recorded case mismatch: {name}')
    if len(set(actual))!=len(actual):raise RuntimeError(f'Duplicate case: {name}')
    expected=(folder/'protocol.sha256').read_text().strip()
    if hashlib.sha256((folder/'protocol.json').read_bytes()).hexdigest()!=expected:raise RuntimeError(f'Protocol hash mismatch: {name}')
    for r in records:
        job=next(j for j in plan['jobs'] if j['id']==r['id'])
        if any(r.get(k)!=v for k,v in job.items()):raise RuntimeError(f'Case attributes changed: {r["id"]}')
        if json.loads((folder/'episodes'/r['id']/'record.json').read_text())!=r:raise RuntimeError(f'Per-case record differs: {r["id"]}')
        if r['status'] not in ['matched','stale','oracle_error','infrastructure_error']:raise RuntimeError(f'Unknown status: {r["id"]}')
        if r['status'] in ['matched','stale']:
            case_folder=folder/'episodes'/r['id'];ext='.js' if r['tool']=='tsc' else '.html'
            if manifest(case_folder/'observed',ext)!=r['observed_projection']:raise RuntimeError(f'Observed bytes differ: {r["id"]}')
            if manifest(case_folder/'clean/out',ext)!=r['clean']['projection']:raise RuntimeError(f'Clean bytes differ: {r["id"]}')
            for tree in ['work','clean']:
                if source_hash(case_folder/tree,r['tool'])!=r['clean']['source_sha256']:raise RuntimeError(f'Final source hash differs: {r["id"]}')
            if r['tool']=='tsc' and (case_folder/'work/tsconfig.json').read_bytes()!=(case_folder/'clean/tsconfig.json').read_bytes():raise RuntimeError(f'Compiler options differ: {r["id"]}')
            if r.get('ready_ns') is not None and not r['ready_ns']<=r['edit']['start_ns']<=r['edit']['end_ns']:raise RuntimeError(f'Readiness/edit clock order: {r["id"]}')
            if r['clean']['returncode']!=0:raise RuntimeError(f'Invalid oracle: {r["id"]}')
            equal=r['observed_projection']==r['clean']['projection']
            if equal!=(r['status']=='matched'):raise RuntimeError(f'Endpoint misclassification: {r["id"]}')
            for check in ['snapshot_stable','obligation_consistent','served_matches_disk']:
                if r.get(check) is False:raise RuntimeError(f'{check} failed: {r["id"]}')
            if r.get('stable_latency_ms') is not None and (r['status']!='matched' or not r['edit']['obligation']):raise RuntimeError(f'Invalid latency: {r["id"]}')
            for k,v in r.get('metrics',{}).items():
                if v<0:raise RuntimeError(f'Negative metric {k}: {r["id"]}')
    return records

def quantile(values,p):
    a=sorted(values)
    if not a:return None
    position=(len(a)-1)*p;lo=math.floor(position);hi=math.ceil(position)
    return a[lo]+(a[hi]-a[lo])*(position-lo)

def fmt(x,d=1):return '--' if x is None else f'{x:.{d}f}'
def counts(rs):return dict(collections.Counter(r['status'] for r in rs))
def passed(rs):return sum(r['status']=='matched' for r in rs)
def stale(rs):return sum(r['status']=='stale' for r in rs)
def write(path,text):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text+'\n')
def texrow(xs):return ' & '.join(str(x) for x in xs)+r' \\'

def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,default=ROOT/'results');p.add_argument('--paper',type=Path,default=ROOT/'paper-data');a=p.parse_args()
    datasets={name:load(name,a.results) for name in DATASETS};main=datasets['primary-matrix'];out=a.results/'derived';out.mkdir(exist_ok=True);gen=a.paper/'generated'
    summary={'datasets':{k:{'n':len(v),'outcomes':counts(v)} for k,v in datasets.items()},'configurations':[]}
    matrix=[];cost=[]
    for tool,mode,label in CONFIGS:
        rows=[r for r in main if r['tool']==tool and r['mode']==mode]
        ordinary=[r for r in rows if r['scenario']!='preserved_stat'];oblig=[r for r in ordinary if r['edit']['obligation']]
        lat=[r['stable_latency_ms'] for r in oblig if r.get('stable_latency_ms') is not None];cpu=[r['metrics']['cpu_s']*1000 for r in oblig if 'metrics' in r]
        control=[r for r in rows if r['scenario']=='temporary'];noise=sum(r.get('noise_rebuilds',0) for r in control)
        item={'tool':tool,'mode':mode,'label':label,'n':len(rows),'ordinary_n':len(ordinary),'ordinary_matched':passed(ordinary),'ordinary_stale':stale(ordinary),'relevant_n':len(oblig),'relevant_matched':passed(oblig),'latency_median_ms':quantile(lat,.5),'latency_q25_ms':quantile(lat,.25),'latency_q75_ms':quantile(lat,.75),'cpu_median_ms':quantile(cpu,.5),'cpu_q25_ms':quantile(cpu,.25),'cpu_q75_ms':quantile(cpu,.75),'noise_builds':noise,'control_n':len(control),'metadata_matched':passed([r for r in rows if r['scenario']=='preserved_stat']),'scan_bytes_median':quantile([r['metrics']['scan_bytes'] for r in oblig],.5),'scan_calls_median':quantile([r['metrics']['scan_calls'] for r in oblig],.5),'storage_in_median_blocks':quantile([r['metrics']['storage_in_blocks'] for r in oblig],.5),'storage_out_median_blocks':quantile([r['metrics']['storage_out_blocks'] for r in oblig],.5),'failed_builds':sum(r['metrics']['failed_builds'] for r in rows),'additional_builds':sum(r['additional_builds'] for r in oblig)}
        summary['configurations'].append(item)
        matrix.append(texrow([label]+[f"{stale([r for r in rows if r['scenario']==s])}/{len([r for r in rows if r['scenario']==s])}" for s in SCENARIOS]))
        cost.append(texrow([label,f"{passed(oblig)}/{len(oblig)}",f"{fmt(quantile(lat,.5))} [{fmt(quantile(lat,.25))}, {fmt(quantile(lat,.75))}]",fmt(quantile(cpu,.5)),f'{noise}/{len(control)}']))
        cdf='ms fraction\n'+'\n'.join(f'{x:.3f} {sum(v<=x for v in lat)/len(oblig):.8f}' for x in [0]+sorted(set(lat))+[1500])
        write(gen/f'cdf-{tool}-{mode}.dat',cdf)
    matrixtex=r'''\begin{table*}[t]
\centering
\caption{Stale endpoints within 1.5 seconds after editing (count / six trials per cell). The last column is a metadata-preservation stress stratum, not an ordinary-save failure rate. An endpoint mismatch is not necessarily permanent event loss.}
\label{tab:matrix}
\begin{tabular}{lrrrrrrrr}
\toprule
Configuration & In place & Rename & Burst & New dir. & Temp. & Same size & Chunked & Restore time\\
\midrule
'''+ '\n'.join(matrix)+r'''
\bottomrule
\end{tabular}
\end{table*}'''
    write(gen/'matrix.tex',matrixtex)
    write(gen/'cost.tex',r'''\begin{table*}[t]
\centering
\caption{Ordinary relevant-edit responses and work. Success is over 36 episodes per row; latency is median [25th, 75th percentile] among successful endpoints only. CPU is median per episode over all 36, in milliseconds. The last column counts rebuild attempts across six output-neutral temporary-file episodes, not failed controls.}
\label{tab:cost}
\begin{tabular}{llrrr}
\toprule
Configuration & Success & Latency (ms) & CPU (ms) & Noise builds / controls\\
\midrule
'''+ '\n'.join(cost)+r'''
\bottomrule
\end{tabular}
\end{table*}''')
    sensitivity=datasets['sensitivity'];groups=collections.defaultdict(list)
    for r in sensitivity:groups[(r['tool'],r['mode'],r.get('inject','none'))].append(r)
    senrows=[]
    for (tool,mode,inject),rs in sorted(groups.items()):
        repaired=sum(r.get('manual_rebuild_matches') is True for r in rs)
        senrows.append(texrow([f'{tool}: {mode.replace("_"," ")}',inject,f'{stale(rs)}/{len(rs)}',f'{repaired}/{stale(rs)}' if stale(rs) else '--']))
    write(gen/'sensitivity.tex',r'''\begin{table}[t]
\centering
\caption{Separate sensitivity controls; no injected case contributes to the natural-scheduling matrix. Repair counts refer only to stale endpoints and a manual rebuild.}
\label{tab:sensitivity}
\begin{tabular}{llrr}\toprule
Configuration & Injection & Stale & Repaired\\\midrule
'''+ '\n'.join(senrows)+r'''
\bottomrule\end{tabular}
\end{table}''')
    timing=datasets['timing-diagnostic'];timrows=[]
    for mode,condition in [('poll','same_second'),('poll','cross_second'),('relevant','same_second'),('relevant','cross_second'),('hash','same_second')]:
        rs=[r for r in timing if r['mode']==mode and r['condition']==condition]
        proper=sum(r.get('same_second')==(condition=='same_second') and r.get('mtime_changed') and r.get('size_unchanged') for r in rs)
        timrows.append(texrow([mode,condition.replace('_',' '),f'{proper}/{len(rs)}',f'{stale(rs)}/{len(rs)}']))
    write(gen/'timing.tex',r'''\begin{table}[t]
\centering
\caption{Post-discovery timing diagnostic, with a 3-second endpoint and normal same-size writes. ``Aligned'' verifies the planned second boundary, changed nanosecond mtime, and equal size; no timestamps are restored.}
\label{tab:timing}
\begin{tabular}{llrr}\toprule
Docs mode & Timing & Aligned & Stale\\\midrule
'''+ '\n'.join(timrows)+r'''
\bottomrule\end{tabular}
\end{table}''')
    extr=[]
    for scenario,label in [('atomic','Rename'),('burst','Burst'),('newdir','New dir.')]:
        g=[r for r in datasets['baseline-challenge'] if r['scenario']==scenario]
        lat=[r['stable_latency_ms'] for r in g if r.get('stable_latency_ms') is not None]
        extr.append(texrow(['Sync native',label,'1.5',f'{passed(g)}/{len(g)}',fmt(quantile(lat,.5))]))
    for mode,label in [('default','Default'),('poll','Polling')]:
        g=[r for r in datasets['long-budget'] if r['mode']==mode]
        lat=[r['stable_latency_ms'] for r in g if r.get('stable_latency_ms') is not None]
        extr.append(texrow([label,'New dir.','5.0',f'{passed(g)}/{len(g)}',fmt(quantile(lat,.5))]))
    write(gen/'challenge.tex',r'''\begin{table}[t]
\centering
\caption{Separate baseline/deadline challenges. Synchronous native options use the fuller documented configuration. Five-second cases are fresh replays, not continuations of the main trials. Latency is conditional on success.}
\label{tab:challenge}
\begin{tabular}{llrrr}\toprule
Mode & Edit & Budget (s) & Pass & Median (ms)\\\midrule
'''+ '\n'.join(extr)+r'''
\bottomrule\end{tabular}
\end{table}''')
    uvrows=[];uv=datasets['uvicorn-integration']
    for mode,scenario in [('default','same_size'),('include_md','same_size'),('include_md','atomic'),('include_md','temporary')]:
        rs=[r for r in uv if r['mode']==mode and r['scenario']==scenario]
        uvrows.append(texrow([mode.replace('_',' '),scenario.replace('_',' '),f'{passed(rs)}/{len(rs)}',sum(r.get('rerenders',0) for r in rs)]))
    write(gen/'uvicorn.tex',r'''\begin{table}[t]
\centering
\caption{Actual Uvicorn CLI integration (1.5-second endpoint). A Markdown dependency is outside the default Python-only reload selection. Renders are post-readiness attempts across each row, not production measurements.}
\label{tab:uvicorn}
\begin{tabular}{llrr}\toprule
Selection & Edit & Success & Renders\\\midrule
'''+ '\n'.join(uvrows)+r'''
\bottomrule\end{tabular}
\end{table}''')
    native=[r for r in main if r['scenario']!='preserved_stat' and ((r['tool']=='tsc' and r['mode'] in ['default','recommended']) or (r['tool']=='docs' and r['mode'] in ['default','relevant','tuned']))]
    macros={'MainN':len(main),'TimingN':len(timing),'NativeN':len(native),'NativePass':passed(native),'NativeOrdinaryResult':f'The native-notification configurations meet {passed(native)} of {len(native)} ordinary endpoint obligations.','NativeZeroBound':f'{(1-.05**(1/len(native)))*100:.1f}', 'MainStale':stale(main),'MainInfrastructure':sum(r['status']=='infrastructure_error' for r in main)}
    for item in summary['configurations']:
        prefix=('TS' if item['tool']=='tsc' else 'Docs')+item['mode'].capitalize()
        for key in ['ordinary_matched','ordinary_stale','noise_builds','metadata_matched','relevant_matched','additional_builds']:
            macros[prefix+''.join(x.capitalize() for x in key.split('_'))]=item[key]
        for key in ['latency_median_ms','cpu_median_ms','scan_bytes_median','scan_calls_median']:
            macros[prefix+''.join(x.capitalize() for x in key.split('_'))]=fmt(item[key])
    write(gen/'numbers.tex','% Generated from complete raw records; do not hand-edit.\n'+'\n'.join('\\newcommand{\\'+k+'}{'+str(v)+'}' for k,v in macros.items()))
    write(out/'summary.json',json.dumps(summary,indent=2))
    with (out/'configurations.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(summary['configurations'][0]));w.writeheader();w.writerows(summary['configurations'])
    with (out/'episodes.csv').open('w',newline='') as f:
        names=['dataset','id','tool','mode','scenario','condition','status','stable_latency_ms','cpu_s','builds','failed_builds','noise_rebuilds','scan_calls','scan_bytes','storage_in_blocks','storage_out_blocks']
        w=csv.DictWriter(f,fieldnames=names);w.writeheader()
        for dataset,rs in datasets.items():
            for r in rs:
                row={k:r.get(k,'') for k in names};row['dataset']=dataset
                row.update({k:r.get('metrics',{}).get(k,'') for k in ['cpu_s','builds','failed_builds','scan_calls','scan_bytes','storage_in_blocks','storage_out_blocks']});w.writerow(row)
    validation={'planned_episode_match':True,'duplicate_ids':False,'protocol_hashes_match':True,'per_episode_records_match':True,'classifications_match_raw_projections':True,'retained_output_bytes_match_hashes':True,'identical_final_source_and_compiler_config':True,'planned_attributes_match':True,'available_invariants_hold':True,'datasets':summary['datasets'],'source_hashes':{}}
    original=json.loads((ROOT/'protocols/primary-matrix-source-sha256.json').read_text())
    current_manifest=json.loads((ROOT/'evidence/source-revision-audit.json').read_text())['files']
    validation['frozen_archive_hashes']={}
    validation['current_source_manifest']=current_manifest
    with tarfile.open(ROOT/'evidence/primary-matrix-source.tar.gz','r:gz') as archive:
        for path,expected in original.items():
            member=archive.extractfile(path)
            if member is None:raise RuntimeError(f'Missing frozen source: {path}')
            validation['frozen_archive_hashes'][path]=hashlib.sha256(member.read()).hexdigest()==expected
    for path,expected in current_manifest.items():
        source=ROOT/path
        validation['source_hashes'][path]=source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest()==expected
    if not all(validation['source_hashes'].values()) or not all(validation['frozen_archive_hashes'].values()):
        raise RuntimeError('Frozen archive or current implementation differs from its declared manifest')
    write(out/'validation.json',json.dumps(validation,indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
