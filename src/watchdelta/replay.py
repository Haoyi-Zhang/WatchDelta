from __future__ import annotations
import os,time
from pathlib import Path
from .core import TOKEN0
SCENARIOS=['inplace','atomic','burst','newdir','temporary','same_size','chunked','preserved_stat']

def edit(root:Path,tool:str,scenario:str,token:str) -> dict:
    target=root/'src'/('message.ts' if tool=='tsc' else 'index.md')
    old=target.read_bytes(); new=old.replace(TOKEN0.encode(),token.encode())
    if len(token)!=len(TOKEN0): raise ValueError('Tokens must preserve byte length')
    if scenario=='inplace': new += b'// Edited source.\n' if tool=='tsc' else b'\nAn appended paragraph.\n'
    start=time.monotonic_ns(); edits=0
    if scenario in ['inplace','same_size','preserved_stat']:
        stat=target.stat(); target.write_bytes(new); edits=1
        if scenario=='preserved_stat': os.utime(target,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    elif scenario=='atomic':
        temp=target.with_name('.wd-save.tmp'); temp.write_bytes(new); os.replace(temp,target); edits=1
    elif scenario=='burst':
        for i in range(20):
            target.write_bytes(old.replace(TOKEN0.encode(),f'WB{i:010d}'.encode())); edits+=1; time.sleep(.005)
        target.write_bytes(new); edits+=1
    elif scenario=='newdir':
        path=root/'src'/'feature'/('card.ts' if tool=='tsc' else 'card.md'); path.parent.mkdir()
        path.write_text(f'export const card = "{token}";\n' if tool=='tsc' else f'# Feature\n\n{token}\n'); edits=1
    elif scenario=='temporary':
        temp=target.with_name('.wd-edit.tmp')
        for i in range(3): temp.write_text(f'editor buffer {i}\n'); edits+=1; time.sleep(.02)
        temp.unlink(); edits+=1
    elif scenario=='chunked':
        with target.open('wb') as f:
            half=len(new)//2; f.write(new[:half]); f.flush(); time.sleep(.12); f.write(new[half:]); f.flush()
        edits=2
    else: raise ValueError(scenario)
    end=time.monotonic_ns()
    return {'start_ns':start,'end_ns':end,'writes':edits,'obligation':scenario!='temporary',
            'same_size':len(old)==len(new),'mtime_restored':scenario=='preserved_stat'}
