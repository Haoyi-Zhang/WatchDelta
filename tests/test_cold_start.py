"""Cold-start regression for direct script execution from an unpacked checkout."""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    "analyze_diagnostics.py",
    "analyze_compound_scaling.py",
    "analyze_panel.py",
    "baseline_challenge.py",
    "compound_diagnosis.py",
    "diagnosis_study.py",
    "long_budget.py",
    "scaling_small.py",
    "scaling_large.py",
    "timing_diagnostic.py",
    "uvicorn_integration.py",
)


class ColdStartTests(unittest.TestCase):
    def test_watchdelta_scripts_import_without_pythonpath(self) -> None:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        for name in SCRIPTS:
            script = ROOT / "scripts" / name
            code = (
                "import runpy; "
                f"runpy.run_path({str(script)!r}, run_name='watchdelta_cold_start_smoke')"
            )
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=f"{name} failed cold-start import:\n{result.stdout}\n{result.stderr}",
            )


if __name__ == "__main__":
    unittest.main()
