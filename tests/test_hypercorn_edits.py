"""Timestamp boundaries in the reload regression fixture."""
from pathlib import Path
import os
import tempfile
import unittest

from scripts.hypercorn_integration import TOKEN0, apply_edit, fresh_import, render_app


class HypercornEditTests(unittest.TestCase):
    def test_fractional_timestamp_change_preserves_cache_second(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'app.py'
            source.write_text(render_app(TOKEN0), encoding='utf-8')
            stamp = 1_700_000_000_100_000_000
            os.utime(source, ns=(stamp, stamp))
            token = 'WD0000000007'
            edit = apply_edit(root, 'same_second', token)
            self.assertTrue(edit['same_size'])
            self.assertTrue(edit['same_timestamp_second'])
            self.assertFalse(edit['mtime_restored'])
            self.assertGreater(edit['mtime_after_ns'], edit['mtime_before_ns'])
            self.assertEqual(fresh_import(root)['content'], token)

    def test_inplace_control_invalidates_byte_length(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'app.py').write_text(render_app(TOKEN0), encoding='utf-8')
            edit = apply_edit(root, 'inplace', 'WD0000000005')
            self.assertFalse(edit['same_size'])
            self.assertEqual(fresh_import(root)['content'], 'WD0000000005')


if __name__ == '__main__':
    unittest.main()
