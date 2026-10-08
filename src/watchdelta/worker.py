from __future__ import annotations
import argparse,http.server,json,os,resource,shutil,subprocess,sys,threading,time
from pathlib import Path
from typing import Any
from .core import build_once, projection, source_fingerprint, tsc_path, tsc_command
LOCK=threading.Lock(); STOP=threading.Event(); ACTIVE: subprocess.Popen[str] | None = None
COUNTERS={'scan_bytes':0,'scan_calls':0,'builds':0,'failed_builds':0,'batches':0,'accepted_events':0}

def emit(kind: str, **kwargs: Any) -> None:
    with LOCK: print(json.dumps({'kind':kind,'t_ns':time.monotonic_ns(),**kwargs},sort_keys=True),flush=True)

def metrics() -> dict[str, Any]:
    r=resource.getrusage(resource.RUSAGE_SELF); c=resource.getrusage(resource.RUSAGE_CHILDREN)
    active_cpu=0.0; active_r=0; active_w=0
    if ACTIVE is not None and ACTIVE.poll() is None:
        try:
            stat=Path(f'/proc/{ACTIVE.pid}/stat').read_text().split(') ',1)[1].split()
            active_cpu=(int(stat[11])+int(stat[12]))/os.sysconf('SC_CLK_TCK')
            io=dict(line.split(': ',1) for line in Path(f'/proc/{ACTIVE.pid}/io').read_text().splitlines())
            active_r=int(io.get('read_bytes',0))//512; active_w=int(io.get('write_bytes',0))//512
        except (OSError,IndexError,ValueError): pass
    return {'cpu_s':r.ru_utime+r.ru_stime+c.ru_utime+c.ru_stime+active_cpu,
            'storage_in_blocks':r.ru_inblock+c.ru_inblock+active_r,
            'storage_out_blocks':r.ru_oublock+c.ru_oublock+active_w,**COUNTERS}

def commands() -> None:
    for line in sys.stdin:
        if line.strip()=='stats': emit('stats',metrics=metrics())
        elif line.strip()=='stop': STOP.set(); return

def build(root: Path, tool: str, fail: bool=False) -> None:
    global ACTIVE
    COUNTERS['builds']+=1; emit('build_start')
    if fail:
        COUNTERS['failed_builds']+=1; emit('build_end',returncode=42,injected=True); return
    if tool=='docs': emit('build_end',returncode=0,work=build_once(root,tool))
    else:
        ACTIVE=subprocess.Popen([*tsc_command(),'--project',str(root/'tsconfig.json'),'--pretty','false'],
                                cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        output,_=ACTIVE.communicate(timeout=30); rc=ACTIVE.returncode; ACTIVE=None
        if rc: COUNTERS['failed_builds']+=1
        emit('build_end',returncode=rc,log=output)

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args: Any) -> None: pass

def main() -> None:
    global ACTIVE
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True)
    p.add_argument('--tool',choices=['tsc','docs'],required=True); p.add_argument('--mode',required=True)
    p.add_argument('--inject',default='none'); a=p.parse_args(); root=a.root.resolve()
    injections={value for value in a.inject.split(',') if value and value!='none'}
    allowed={'drop','fail','publish_stale','corrupt_output'}
    unknown=injections-allowed
    if unknown: raise ValueError(f'Unknown injection(s): {sorted(unknown)}')
    threading.Thread(target=commands,daemon=True).start()
    if a.tool=='docs':
        from functools import partial
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(root/'out')))
        threading.Thread(target=server.serve_forever,daemon=True).start(); emit('http',port=server.server_port)
    if a.tool=='tsc' and a.mode!='hash':
        ACTIVE=subprocess.Popen([*tsc_command(),'--project',str(root/'tsconfig.json'),
            '--watch','--pretty','false','--preserveWatchOutput'],cwd=root,
            text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=1); ready=False
        try:
            assert ACTIVE.stdout is not None
            for line in ACTIVE.stdout:
                emit('tool_log',text=line.rstrip())
                if 'Starting compilation in watch mode' in line or 'Starting incremental compilation' in line:
                    COUNTERS['builds']+=1; emit('build_start')
                if 'Watching for file changes.' in line:
                    good='Found 0 errors.' in line
                    if not good: COUNTERS['failed_builds']+=1
                    emit('build_end',returncode=0 if good else 1)
                    if not ready and good: ready=True; emit('ready',metrics=metrics())
        finally:
            if ACTIVE and ACTIVE.poll() is None: ACTIVE.terminate(); ACTIVE.wait(timeout=5)
        return
    build(root,a.tool)
    if a.mode=='hash':
        previous,n=source_fingerprint(root,a.tool); COUNTERS['scan_calls']+=1; COUNTERS['scan_bytes']+=n
        emit('ready',metrics=metrics())
        while not STOP.wait(.1):
            current,n=source_fingerprint(root,a.tool); COUNTERS['scan_calls']+=1; COUNTERS['scan_bytes']+=n
            if current!=previous: previous=current; COUNTERS['batches']+=1; build(root,a.tool)
        return
    from watchfiles import watch, DefaultFilter
    default=DefaultFilter()
    def relevant(change: Any, path: str) -> bool:
        return default(change,path) and path.endswith('.md') and not Path(path).name.startswith('.')
    def wrong(change: Any, path: str) -> bool:
        return relevant(change,path) and not path.endswith('/index.md')
    filt=default if a.mode in ['default','blind_default'] else wrong if a.mode=='wrong_filter' else relevant
    options: dict[str,Any]={'watch_filter':filt,'stop_event':STOP,'yield_on_timeout':True,'rust_timeout':50}
    if a.mode=='tuned': options.update(debounce=200,step=100)
    if a.mode=='poll': options.update(force_polling=True,poll_delay_ms=100)
    watch_root=root/'src'
    if a.mode in ['blind','blind_default']:
        watch_root=root/'unrelated'; watch_root.mkdir(exist_ok=True)
    ready=False; consumed:set[str]=set()
    for changes in watch(watch_root,**options):
        if not ready: ready=True; emit('ready',metrics=metrics())
        if not changes: continue
        COUNTERS['batches']+=1; COUNTERS['accepted_events']+=len(changes)
        emit('events',events=sorted((int(c),os.path.relpath(f,root)) for c,f in changes))
        if 'drop' in injections and 'drop' not in consumed:
            consumed.add('drop'); emit('injected_drop'); continue
        fail='fail' in injections and 'fail' not in consumed
        if 'publish_stale' in injections and 'publish_stale' not in consumed and not fail:
            consumed.add('publish_stale'); COUNTERS['builds']+=1; emit('build_start')
            stage=root/'.wd-unpublished'
            if stage.exists(): shutil.rmtree(stage)
            shutil.copytree(root/'src',stage/'src'); (stage/'out').mkdir(parents=True)
            result=build_once(stage,a.tool)
            emit('build_end',returncode=0,published=False,work=result,unpublished_projection=projection(stage/'out','.html'))
            continue
        if fail: consumed.add('fail')
        build(root,a.tool,fail)
        if not fail and 'corrupt_output' in injections and 'corrupt_output' not in consumed:
            consumed.add('corrupt_output')
            suffix='.html' if a.tool=='docs' else '.js'
            candidates=sorted((root/'out').rglob('*'+suffix))
            if not candidates: raise RuntimeError('No output available for corruption injection')
            target=candidates[0]
            target.write_bytes(target.read_bytes()+b'\n/* watchdelta injected post-build corruption */\n')
            emit('post_build_corruption',path=str(target.relative_to(root)))
if __name__=='__main__':
    try: main()
    except Exception as exc: emit('worker_error',error=repr(exc)); raise
