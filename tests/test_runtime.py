"""Actual one-shot compiler/renderer oracle checks; not watcher reliability trials."""
import json,tempfile,unittest
from pathlib import Path
from watchdelta.core import build_once,clean_build,create_fixture,endpoint_status,projection,TOKEN0

class RuntimeOracleTests(unittest.TestCase):
    def test_typescript_two_independent_clean_builds_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';create_fixture(root,'tsc','default')
            first=clean_build(root,'tsc',Path(tmp)/'first');second=clean_build(root,'tsc',Path(tmp)/'second')
            self.assertEqual(first['returncode'],0);self.assertEqual(second['returncode'],0)
            self.assertEqual(first['projection'],second['projection'])
            self.assertEqual(first['source_sha256'],second['source_sha256'])
    def test_actual_failed_clean_compilation_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';create_fixture(root,'tsc','default')
            (root/'src/message.ts').write_text('export const message: number = "not a number";\n')
            clean=clean_build(root,'tsc',Path(tmp)/'clean')
            self.assertNotEqual(clean['returncode'],0)
            self.assertEqual(endpoint_status({},clean['projection'],False),'oracle_error')
    def test_two_fresh_markdown_processes_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';create_fixture(root,'docs','default')
            first=clean_build(root,'docs',Path(tmp)/'first');second=clean_build(root,'docs',Path(tmp)/'second')
            self.assertEqual(first['returncode'],0);self.assertEqual(second['returncode'],0)
            self.assertEqual(first['projection'],second['projection'])
    def test_same_size_changed_token_survives_real_rendering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';create_fixture(root,'docs','default');build_once(root,'docs')
            before=projection(root/'out','.html');source=root/'src/index.md';text=source.read_text();source.write_text(text.replace(TOKEN0,'WD9876543210'));build_once(root,'docs')
            self.assertEqual(len(text),len(source.read_text()));self.assertNotEqual(before,projection(root/'out','.html'))
if __name__=='__main__':unittest.main()
