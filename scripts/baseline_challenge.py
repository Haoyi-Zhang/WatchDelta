"""A separate follow-up of the handbook's synchronous directory option.
The fixture configuration changes; the TypeScript compiler is unmodified.
"""
import json,sys
from pathlib import Path

# Permit direct execution from an unpacked source tree without relying on an
# inherited PYTHONPATH.  Experiment semantics are unchanged.
import sys as _sys
from pathlib import Path as _BootstrapPath
_SRC = _BootstrapPath(__file__).resolve().parents[1] / "src"
if str(_SRC) not in _sys.path:
    _sys.path.insert(0, str(_SRC))
from watchdelta import run
original=run.create_fixture

def documented(root,tool,mode,file_count=None):
    original(root,tool,mode,file_count)
    if mode=='documented_sync':
        p=root/'tsconfig.json';data=json.loads(p.read_text())
        data['watchOptions']={'watchFile':'useFsEvents','watchDirectory':'useFsEvents','fallbackPolling':'dynamicPriority','synchronousWatchDirectory':True,'excludeDirectories':['**/node_modules','_build']}
        p.write_text(json.dumps(data,indent=2)+'\n')
run.create_fixture=documented
if __name__=='__main__':run.main()
