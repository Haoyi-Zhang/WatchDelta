#!/usr/bin/env python3
"""Check the tested execution contract, without fetching anything."""
import argparse,hashlib,importlib.metadata,json,os,platform,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--allow-version-drift',action='store_true');a=p.parse_args()
errors=[];info={'platform':platform.platform(),'python':platform.python_version(),'packages':{}}
if sys.platform!='linux':errors.append('Only Linux was evaluated; process groups and /proc are required.')
for line in (ROOT/'requirements-lock.txt').read_text().splitlines():
 if '==' not in line or line.startswith('#'):continue
 name,expected=line.split('==');actual=None
 try:actual=importlib.metadata.version(name)
 except importlib.metadata.PackageNotFoundError:errors.append(f'Missing dependency: {name}')
 info['packages'][name]=actual
 if actual is not None and actual!=expected:errors.append(f'{name}: expected {expected}, found {actual}')
for command,expected in [('node','v22.16.0'),(os.environ.get('WATCHDELTA_TSC') or shutil.which('tsc'),'Version 5.8.3')]:
 if not command:errors.append('TypeScript missing; install 5.8.3 and set WATCHDELTA_TSC');continue
 try:
  argv = ['node', command, '--version'] if str(command).lower().endswith(('.js','.cjs','.mjs')) else [command,'--version']
  actual=subprocess.check_output(argv,text=True,timeout=10).strip();info[str(command)]=actual
  if actual!=expected:errors.append(f'{command}: expected {expected}, found {actual}')
 except (OSError,subprocess.SubprocessError) as e:errors.append(str(e))
if platform.python_version()!='3.13.5':errors.append('Tested interpreter is CPython 3.13.5; record any different version as a new environment.')
watch_keys=['TSC_WATCHFILE','TSC_WATCHDIRECTORY','TSC_NONPOLLING_WATCHER','WATCHFILES_FORCE_POLLING','WATCHFILES_POLL_DELAY_MS']
info['watch_overrides']={k:os.environ.get(k) for k in watch_keys}
if any(info['watch_overrides'].values()):errors.append('Unset external watch overrides to reproduce the recorded baseline configurations.')
info['issues']=errors;print(json.dumps(info,indent=2))
if errors and not a.allow_version_drift:raise SystemExit(2)
