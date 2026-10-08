"""Regression tests for the cache-contaminated reference exposed by the Hypercorn pilot."""
from __future__ import annotations
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

class PythonCacheOracleTests(unittest.TestCase):
    def test_restored_mtime_same_size_can_fool_import_but_not_direct_compile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);module=root/'candidate.py'
            old='CONTENT = "WD0000000000"\n';new='CONTENT = "WD0000000001"\n'
            self.assertEqual(len(old),len(new));module.write_text(old)
            import_cmd=[sys.executable,'-c','import candidate; print(candidate.CONTENT)']
            cached_env = os.environ.copy()
            cached_env.pop('PYTHONDONTWRITEBYTECODE', None)
            first=subprocess.run(import_cmd,cwd=root,text=True,capture_output=True,check=True,env=cached_env)
            self.assertEqual(first.stdout.strip(),'WD0000000000')
            pycache=list((root/'__pycache__').glob('candidate.*.pyc'))
            self.assertEqual(len(pycache),1)
            stat=module.stat();module.write_text(new);os.utime(module,ns=(stat.st_atime_ns,stat.st_mtime_ns))
            imported=subprocess.run(import_cmd,cwd=root,text=True,capture_output=True,check=True,env=cached_env)
            # CPython's default timestamp/size cache validation can accept the old bytecode.
            self.assertEqual(imported.stdout.strip(),'WD0000000000')
            code=("import pathlib,sys; p=pathlib.Path(sys.argv[1]); ns={}; "
                  "exec(compile(p.read_bytes(),str(p),'exec'),ns); print(ns['CONTENT'])")
            direct=subprocess.run([sys.executable,'-c',code,str(module)],cwd=root,text=True,
                                  capture_output=True,check=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
            self.assertEqual(direct.stdout.strip(),'WD0000000001')

    def test_hypercorn_protocol_declares_isolated_oracle(self):
        root=Path(__file__).resolve().parents[1]
        protocol=json.loads((root/'protocols/hypercorn-integration.json').read_text())
        self.assertIn('PYTHONDONTWRITEBYTECODE=1',protocol['oracle'])
        self.assertIn('directly',protocol['oracle'])

if __name__=='__main__':unittest.main()
