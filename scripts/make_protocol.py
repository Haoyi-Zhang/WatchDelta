import json,datetime
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def save(name,jobs,repetitions):
 data={'id':name,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'scope':'Local Linux overlay; real tsc watch and watchfiles + markdown-it-py; no MkDocs/Vite runtime claim',
 'settle_seconds':1.5,'sampler_seconds':0.02,'scan_interval_seconds':0.1,
 'repetitions':repetitions,'random_seed':290926,'oracle':'Exact relative output path set and SHA-256 bytes; identity normalization; fresh one-shot build of final copied sources',
 'latency':'first sample in final matching suffix, lower bounded by edit completion; not defined for no-op controls or stale outcomes',
 'noise':'build attempts in output-neutral temporary-file episodes; extra builds during relevant bursts are not called unnecessary',
 'stop_rule':'fixed job list; infrastructure failures retained; no outcome-adaptive repetition','jobs':jobs}
 (root/'protocols'/f'{name}.json').write_text(json.dumps(data,indent=2)+'\n')
if __name__=='__main__':
 jobs=[]
 for i,(tool,mode,scenario) in enumerate([('tsc','default','inplace'),('tsc','default','preserved_stat'),('tsc','poll','preserved_stat'),('tsc','hash','preserved_stat'),('docs','default','temporary'),('docs','relevant','temporary'),('docs','default','inplace'),('docs','poll','preserved_stat'),('docs','hash','preserved_stat')]):
  jobs.append({'id':f'pilot-{i:03d}-{tool}-{mode}-{scenario}','numeric_id':i+1,'tool':tool,'mode':mode,'scenario':scenario,'replicate':0,'stratum':'pilot'})
 save('pilot',jobs,1)
