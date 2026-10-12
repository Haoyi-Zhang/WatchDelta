"""Real local subprocess repair, without the injection/truth mapping harness."""
from pathlib import Path
import tempfile
import unittest

from scripts.local_unknown import Session, endpoint, repair


class LocalUnknownTests(unittest.TestCase):
    def test_literal_reconfiguration_repairs_both_blinded_configurations(self):
        for scope, suffix in (("src", ".txt"), ("unrelated", ".md")):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "src").mkdir()
                (root / "unrelated").mkdir()
                source = root / "src/input.md"
                # Preserve CRLF to catch unintended read_text normalization.
                source.write_bytes(b"initial\r\n")
                session = Session(root, scope, suffix)
                try:
                    source.write_bytes(b"terminal\r\n")
                    expected = b"TERMINAL\r\n".decode("utf-8")
                    self.assertFalse(endpoint(session, expected, .03)["matched"])
                    actions = repair(session, expected, "configured")
                    self.assertIn("selection", actions)
                    self.assertTrue(endpoint(session, expected, .03)["matched"])
                    source.write_bytes(b"followup\r\n")
                    self.assertTrue(endpoint(session, "FOLLOWUP\r\n", .03)["matched"])
                finally: session.stop()

    def test_manual_build_repairs_once_but_not_observer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "unrelated").mkdir()
            source = root / "src/input.md"
            source.write_bytes(b"initial\n")
            session = Session(root, "src", ".txt")
            try:
                source.write_bytes(b"first\n")
                repair(session, "FIRST\n", "manual")
                self.assertTrue(endpoint(session, "FIRST\n", .03)["matched"])
                source.write_bytes(b"second\n")
                self.assertFalse(endpoint(session, "SECOND\n", .03)["matched"])
            finally: session.stop()
