from __future__ import annotations
import hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
from typing import Any
TOKEN0 = 'WD0000000000'

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def projection(folder: Path, extension: str) -> dict[str, str]:
    """Identity-normalized, path-sensitive byte hashes; no source token stripping."""
    if not folder.exists(): return {}
    answer = {}
    for p in sorted(folder.rglob('*' + extension)):
        if p.is_symlink(): raise ValueError('Symlink outside the declared small-tree contract')
        if p.is_file():
            try: answer[p.relative_to(folder).as_posix()] = digest(p.read_bytes())
            except FileNotFoundError: continue
    return answer

def source_files(root: Path, tool: str) -> list[Path]:
    ext = '.ts' if tool == 'tsc' else '.md'
    return sorted(p for p in (root / 'src').rglob('*' + ext)
                  if p.is_file() and not any(x.startswith('.') for x in p.relative_to(root/'src').parts))

def source_fingerprint(root: Path, tool: str) -> tuple[str, int]:
    h = hashlib.sha256(); total = 0
    for p in source_files(root, tool):
        if p.is_symlink(): raise ValueError('Symlinks not supported')
        data = p.read_bytes(); name = p.relative_to(root).as_posix().encode()
        h.update(len(name).to_bytes(8, 'big')); h.update(name)
        h.update(len(data).to_bytes(8, 'big')); h.update(data); total += len(data)
    return h.hexdigest(), total

def module_subprocess_env() -> dict[str, str]:
    """Make checked-out modules importable in fresh child processes.

    A source-layout checkout can import ``watchdelta`` in pytest without being
    installed, but ``python -m watchdelta...`` starts with a new ``sys.path``.
    Prepending this checkout's ``src`` directory keeps the child process
    independent while making the repository genuinely runnable after unzip.
    Existing caller settings are preserved.
    """
    env = os.environ.copy()
    src_root = str(Path(__file__).resolve().parents[1])
    current = env.get('PYTHONPATH', '')
    parts = [p for p in current.split(os.pathsep) if p]
    if src_root not in parts:
        env['PYTHONPATH'] = os.pathsep.join([src_root, *parts])
    return env

def tsc_path() -> str:
    candidate = os.environ.get('WATCHDELTA_TSC') or shutil.which('tsc')
    if not candidate: raise RuntimeError('TypeScript 5.8.3 is required; set WATCHDELTA_TSC')
    return candidate

def tsc_command() -> list[str]:
    candidate = tsc_path()
    if candidate.endswith(('.js', '.cjs', '.mjs')):
        node = os.environ.get('WATCHDELTA_NODE') or shutil.which('node')
        if not node: raise RuntimeError('Node.js is required for the TypeScript compiler')
        return [node, candidate]
    return [candidate]

def create_fixture(root: Path, tool: str, mode: str, file_count: int | None = None) -> None:
    (root / 'src').mkdir(parents=True)
    if file_count is not None and file_count < (2 if tool == 'tsc' else 1):
        raise ValueError('file_count is smaller than the fixture minimum')
    if tool == 'tsc':
        (root/'src/message.ts').write_text(f'export const message = "{TOKEN0}";\n')
        (root/'src/index.ts').write_text('import { message } from "./message";\nconsole.log(JSON.stringify({message}));\n')
        for i in range(max(0, (file_count or 2) - 2)):
            path = root/'src'/'modules'/f'module_{i:04d}.ts'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f'export const value_{i:04d} = {i};\n')
        cfg: dict[str, Any] = {'compilerOptions': {'target':'ES2020', 'module':'CommonJS', 'strict':True,
                'rootDir':'src','outDir':'out','skipLibCheck':True,'types':[], 'noEmitOnError':True},
                'include':['src/**/*.ts']}
        if mode == 'recommended':
            cfg['watchOptions'] = {'watchFile':'useFsEvents','watchDirectory':'useFsEvents', 'fallbackPolling':'dynamicPriority'}
        elif mode == 'poll':
            cfg['watchOptions'] = {'watchFile':'fixedPollingInterval','watchDirectory':'fixedPollingInterval'}
        elif mode == 'wrong_filter': cfg['watchOptions'] = {'excludeFiles':['./src/message.ts']}
        (root/'tsconfig.json').write_text(json.dumps(cfg,indent=2)+'\n')
    else:
        (root/'src/index.md').write_text('# Development guide\n\n'+TOKEN0+'\n\nA **small** documentation fixture.\n')
        for i in range(max(0, (file_count or 1) - 1)):
            path = root/'src'/'pages'/f'page_{i:04d}.md'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f'# Page {i}\n\nStable page {i}.\n')
    (root/'out').mkdir()

def build_docs(root: Path, output: Path | None = None) -> dict[str, int]:
    """Real markdown-it-py rendering; no synthetic event emitter or fake build."""
    from markdown_it import MarkdownIt
    renderer = MarkdownIt('commonmark', {'html':False}); count, total = 0, 0
    output = output or root/'out'
    output.mkdir(parents=True, exist_ok=True)
    expected: set[Path] = set()
    for p in source_files(root, 'docs'):
        data = p.read_bytes(); total += len(data)
        target = output/p.relative_to(root/'src').with_suffix('.html')
        expected.add(target.resolve())
        target.parent.mkdir(parents=True,exist_ok=True)
        rendered = '<!doctype html>\n<meta charset="utf-8">\n' + renderer.render(data.decode('utf-8'))
        stage = target.with_suffix('.html.wd-stage')
        stage.write_text(rendered,encoding='utf-8'); os.replace(stage,target); count += 1
    removed = 0
    for stale in sorted(output.rglob('*.html')):
        if stale.resolve() not in expected:
            stale.unlink(); removed += 1
    return {'source_bytes':total,'source_files':count,'removed_outputs':removed}

def build_once(root: Path, tool: str) -> subprocess.CompletedProcess[str] | dict[str, int]:
    if tool == 'docs': return build_docs(root)
    return subprocess.run([*tsc_command(),'--project',str(root/'tsconfig.json'),'--pretty','false'],
                          cwd=root,text=True,capture_output=True,timeout=30)

def clean_build(root: Path, tool: str, dest: Path) -> dict[str, Any]:
    """Fresh output dir/process using identical, hashed final source tree."""
    before = source_fingerprint(root,tool)[0]; shutil.copytree(root/'src',dest/'src')
    if tool == 'tsc': shutil.copy2(root/'tsconfig.json',dest/'tsconfig.json')
    cmd = [sys.executable,'-m','watchdelta.build','--root',str(dest),'--tool',tool]
    result = subprocess.run(cmd,capture_output=True,text=True,timeout=35,env=module_subprocess_env())
    after = source_fingerprint(root,tool)[0]
    if before != after or source_fingerprint(dest,tool)[0] != before:
        raise RuntimeError('Final source tree changed across clean-build boundary')
    return {'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,
            'source_sha256':before,'projection':projection(dest/'out','.js' if tool=='tsc' else '.html'),
            'command':[sys.executable,'-m','watchdelta.build','--root','<clean>','--tool',tool]}

def endpoint_status(observed: dict[str,str], expected: dict[str,str], clean_ok: bool) -> str:
    if not clean_ok: return 'oracle_error'
    return 'matched' if observed == expected else 'stale'

def stable_latency(timeline: list[dict[str,Any]], expected: dict[str,str], edit_end_ns: int,
                   obligation: bool) -> float | None:
    """First matching sample in final uninterrupted matching suffix."""
    if not obligation or not timeline or timeline[-1]['projection'] != expected: return None
    start = len(timeline)-1
    while start > 0 and timeline[start-1]['projection'] == expected: start -= 1
    return (max(edit_end_ns,timeline[start]['t_ns'])-edit_end_ns)/1e6
