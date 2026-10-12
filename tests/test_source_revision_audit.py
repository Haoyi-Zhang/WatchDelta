"""Benign source-identity fixtures; no historical archive or server is run."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts import analyze


class SourceRevisionAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="p121-source-audit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ("protocols", "evidence", "scripts", "tests"):
            (self.root / name).mkdir()
        self.old = b"historical experiment bytes\n"
        self.current = b"current analysis bytes\n"
        self.test = b"current regression bytes\n"
        (self.root / "scripts/helper.py").write_bytes(self.current)
        (self.root / "tests/test_helper.py").write_bytes(self.test)
        digest = lambda data: hashlib.sha256(data).hexdigest()
        (self.root / "protocols/primary-matrix-source-sha256.json").write_text(
            json.dumps({"scripts/helper.py": digest(self.old)}), encoding="utf-8")
        (self.root / "evidence/source-revision-audit.json").write_text(json.dumps({
            "files": {"scripts/helper.py": digest(self.current),
                      "tests/test_helper.py": digest(self.test)},
        }), encoding="utf-8")
        self.save_archive(self.old)

    def save_archive(self, data):
        with tarfile.open(self.root / "evidence/primary-matrix-source.tar.gz", "w:gz") as archive:
            member = tarfile.TarInfo("scripts/helper.py")
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))

    def assert_rejected_before_loading_or_writing(self):
        with patch.object(analyze, "ROOT", self.root), \
             patch.object(analyze, "load", side_effect=AssertionError("records loaded before identity check")) as load, \
             patch.object(analyze, "write") as write, \
             patch("sys.argv", ["analyze", "--results", str(self.root / "results"),
                                "--paper", str(self.root / "paper")]):
            with self.assertRaisesRegex(RuntimeError, "differs from its declared manifest"):
                analyze.main()
        load.assert_not_called()
        write.assert_not_called()
        self.assertFalse((self.root / "results/derived").exists())
        self.assertFalse((self.root / "paper").exists())

    def test_separate_current_and_frozen_bytes_are_both_accepted(self):
        audit = analyze.audit_sources(self.root)
        self.assertEqual(audit["frozen_archive_hashes"], {"scripts/helper.py": True})
        self.assertEqual(audit["source_hashes"], {"scripts/helper.py": True, "tests/test_helper.py": True})

    def test_current_source_drift_is_rejected_before_outputs(self):
        (self.root / "scripts/helper.py").write_bytes(b"changed current bytes")
        self.assert_rejected_before_loading_or_writing()

    def test_current_test_drift_is_rejected_before_outputs(self):
        (self.root / "tests/test_helper.py").write_bytes(b"changed regression bytes")
        self.assert_rejected_before_loading_or_writing()

    def test_missing_current_test_is_rejected_before_outputs(self):
        (self.root / "tests/test_helper.py").unlink()
        self.assert_rejected_before_loading_or_writing()

    def test_frozen_archive_drift_is_rejected_before_outputs(self):
        self.save_archive(b"changed historical bytes")
        self.assert_rejected_before_loading_or_writing()


if __name__ == "__main__":
    unittest.main()
