"""Sequential, real Uvicorn CLI reload integration; no mocked observer."""
from __future__ import annotations
import argparse,hashlib,importlib.metadata,json,os,re,shutil,signal,socket,subprocess,sys,time,urllib.error,urllib.request
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
from watchdelta.run import environment
ROOT=Path(__file__).resolve().parents[1]

def registered_root(pid, root):
    """Linux-only readiness evidence from the real reloader's inotify registrations."""
    expected=root.stat().st_ino
    directory=Path(f'/proc/{pid}/fdinfo')
    for item in directory.iterdir():
        try:
            for line in item.read_text().splitlines():
                match=re.search(r'inotify wd:[0-9a-f]+ ino:([0-9a-f]+)',line)
                if match and int(match.group(1),16)==expected:return line
        except (FileNotFoundError,PermissionError):continue
    return None

def main():
    p=argparse.ArgumentParser();p.add_argument('--protocol',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    protocol=json.loads(a.protocol.read_text());a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'protocol.json').write_bytes(a.protocol.read_bytes());(a.output/'protocol.sha256').write_text(hashlib.sha256(a.protocol.read_bytes()).hexdigest()+'\n')
    envinfo=environment();envinfo['uvicorn']=importlib.metadata.version('uvicorn');(a.output/'environment.json').write_text(json.dumps(envinfo,indent=2)+'\n')
    with (a.output/'records.jsonl').open('w') as out:
        for i,job in enumerate(protocol['jobs']):
            folder=(a.output/'episodes'/job['id']).resolve();folder.mkdir(parents=True);work=folder/'work';create_fixture(work,'docs','relevant');record={**job};process=None
            with (folder/'server.log').open('w') as log:
                try:
                    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
                    env=os.environ.copy();env['WATCHDELTA_PROJECT']=str(work)
                    command=[sys.executable,'-m','uvicorn','uvicorn_app:app','--app-dir',str(ROOT/'integrations'),'--host','127.0.0.1','--port',str(port),'--reload','--reload-dir',str(work/'src'),'--no-access-log','--loop','asyncio','--http','h11','--ws','none']
                    if job['mode']=='include_md':command+=['--reload-include','*.md']
                    process=subprocess.Popen(command,cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                    ready_limit=time.monotonic()+20
                    while True:
                        if process.poll() is not None:raise RuntimeError('Uvicorn exited before readiness')
                        try:
                            with urllib.request.urlopen(f'http://127.0.0.1:{port}/index.html',timeout=.3) as r:
                                if b'WD0000000000' in r.read():break
                        except (OSError,urllib.error.URLError):pass
                        if time.monotonic()>ready_limit:raise TimeoutError('Uvicorn readiness')
                        time.sleep(.03)
                    registration=None
                    while registration is None:
                        registration=registered_root(process.pid,work/'src')
                        if time.monotonic()>ready_limit:raise TimeoutError('Uvicorn inotify root registration readiness')
                        if registration is None:time.sleep(.02)
                    ready=time.monotonic_ns();log.flush();initial_renders=(folder/'server.log').read_text().count('WATCHDELTA_RENDER_COMPLETE')
                    info=edit(work,'docs',job['scenario'],f'WD{80000+i:010d}');time.sleep(protocol['settle_seconds'])
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/index.html',timeout=3) as r:served=r.read()
                    observed=projection(work/'out','.html');end=time.monotonic_ns()
                    os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=5);log.flush()
                    shutil.copytree(work/'out',folder/'observed');clean=clean_build(work,'docs',folder/'clean')
                    renders=(folder/'server.log').read_text().count('WATCHDELTA_RENDER_COMPLETE')-initial_renders
                    record.update(status=endpoint_status(observed,clean['projection'],clean['returncode']==0),edit=info,ready_ns=ready,
                      snapshot_stable=projection(folder/'observed','.html')==observed,observer_ready_evidence=registration,observed_projection=observed,clean=clean,served_matches_disk=hashlib.sha256(served).hexdigest()==observed['index.html'],
                      rerenders=renders,observation_ms=(end-info['end_ns'])/1e6,
                      command=[s.replace(str(work),'<project>').replace(str(ROOT),'<artifact>') for s in command])
                except Exception as e:record.update(status='infrastructure_error',error=repr(e))
                finally:
                    if process and process.poll() is None:
                        os.killpg(process.pid,signal.SIGTERM)
                        try:process.wait(timeout=5)
                        except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                    (folder/'record.json').write_text(json.dumps(record,indent=2)+'\n');out.write(json.dumps(record)+'\n');out.flush()
                    print(i+1,len(protocol['jobs']),job['id'],record['status'],record.get('rerenders'),flush=True)
    (a.output/'complete.json').write_text(json.dumps({'episodes':len(protocol['jobs'])},indent=2)+'\n')
if __name__=='__main__':main()
