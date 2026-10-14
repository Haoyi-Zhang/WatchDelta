"""Offline bibliography fixtures; no paper, network or experiment is changed."""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import reference_audit


REFERENCE = """@article{real,
  author = {Fixture Author},
  title = {Fixture reference},
  year = {2020}
}
"""
CONTROL = """@IEEEtranBSTCTL{authorDisplay,
  CTLdash_repeated_names = {no}
}
"""


class ReferenceAuditTests(unittest.TestCase):
    def run_fixture_audit(self, bibliography, key="real"):
        with tempfile.TemporaryDirectory(prefix="p121-bibliography-test-") as directory:
            artifact = Path(directory)
            evidence = artifact / "evidence"
            evidence.mkdir()
            bib_bytes = bibliography.encode("utf-8")
            (evidence / "references.bib").write_bytes(bib_bytes)
            (evidence / "paper-citation-snapshot.json").write_text(json.dumps({
                "bibliography_sha256": hashlib.sha256(bib_bytes).hexdigest(),
                "bibliography_keys": [key],
                "cited_keys": [key],
            }), encoding="utf-8")
            (evidence / "REFERENCE-AUDIT.csv").write_text(
                "key,type,title,year,doi,verification_url,source_type,supports_in_paper\n"
                f"{key},article,Fixture reference,2020,,https://example.org/reference,"
                "official-documentation,Fixture metadata check\n",
                encoding="utf-8",
            )
            (evidence / "REFERENCE-AUDIT.md").write_text("Fixture ledger\n", encoding="utf-8")
            output = io.StringIO()
            with patch.object(reference_audit, "__file__", str(artifact / "scripts/reference_audit.py")), \
                 patch("sys.argv", ["reference_audit", "--expected-count", "1"]), \
                 redirect_stdout(output):
                exit_code = reference_audit.main()
            return exit_code, json.loads(output.getvalue())

    def test_style_control_is_excluded_by_exact_case_insensitive_type(self):
        for entry_type in ("IEEEtranBSTCTL", "ieeetranbstctl", "IeEeTrAnBsTcTl"):
            with self.subTest(entry_type=entry_type):
                control = CONTROL.replace("IEEEtranBSTCTL", entry_type)
                for bibliography in (control + REFERENCE, REFERENCE + control):
                    self.assertEqual(list(reference_audit.parse_bib(bibliography)), ["real"])

    def test_real_control_named_key_and_nearby_type_are_not_excluded(self):
        bibliography = REFERENCE.replace("{real,", "{authorDisplay,")
        bibliography += "@IEEEtranBSTCTLExtra{nearby, title={Not a style control}}\n"
        entries = reference_audit.parse_bib(bibliography)
        self.assertEqual(set(entries), {"authorDisplay", "nearby"})
        self.assertEqual(entries["authorDisplay"]["type"], "article")
        self.assertEqual(entries["nearby"]["type"], "ieeetranbstctlextra")

    def test_unterminated_style_control_is_still_rejected(self):
        with self.assertRaisesRegex(ValueError, "unterminated BibTeX entry: authorDisplay"):
            reference_audit.parse_bib(CONTROL.rstrip().removesuffix("}"))

    def test_style_control_does_not_change_audit_reference_or_citation_counts(self):
        exit_code, result = self.run_fixture_audit(CONTROL + REFERENCE)
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["bibliography_entries"], 1)
        self.assertEqual(result["unique_cited_keys"], 1)
        self.assertTrue(result["audit_key_set_matches"])

    def test_real_reference_missing_title_is_rejected_even_with_control_named_key(self):
        bibliography = REFERENCE.replace("{real,", "{authorDisplay,")
        bibliography = bibliography.replace("  title = {Fixture reference},\n", "")
        exit_code, result = self.run_fixture_audit(bibliography, key="authorDisplay")
        self.assertEqual(exit_code, 1)
        self.assertIn("authorDisplay: missing BibTeX title", result["errors"])

    def test_real_non_misc_reference_still_requires_year_and_author(self):
        for field, expected_error in (
            ("  year = {2020}\n", "real: non-misc entry lacks year"),
            ("  author = {Fixture Author},\n", "real: non-misc entry lacks author/editor"),
        ):
            with self.subTest(field=field):
                exit_code, result = self.run_fixture_audit(CONTROL + REFERENCE.replace(field, ""))
                self.assertEqual(exit_code, 1)
                self.assertIn(expected_error, result["errors"])

    def test_duplicate_real_key_is_rejected_before_dict_overwrite(self):
        with self.assertRaisesRegex(ValueError, "duplicate bibliography key: real"):
            reference_audit.parse_bib(CONTROL + REFERENCE + REFERENCE)

    def test_duplicate_real_key_makes_full_audit_fail(self):
        exit_code, result = self.run_fixture_audit(REFERENCE + REFERENCE)
        self.assertEqual(exit_code, 1)
        self.assertIn("duplicate bibliography key: real", result["errors"])


if __name__ == "__main__":
    unittest.main()
