from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from .core import build_once

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True)
    p.add_argument('--tool',choices=['tsc','docs'],required=True); a=p.parse_args()
    result=build_once(a.root,a.tool)
    if isinstance(result,dict): print(json.dumps(result))
    else:
        print(result.stdout,end=''); print(result.stderr,end='',file=sys.stderr)
        raise SystemExit(result.returncode)
if __name__=='__main__': main()
