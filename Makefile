.PHONY: quickcheck analyze verify replay

quickcheck:
	env -u PYTHONPATH python scripts/preflight.py
	env -u PYTHONPATH python -m pytest -q

analyze:
	env -u PYTHONPATH python scripts/analyze.py --results results --paper /tmp/watchdelta-paper-data
	env -u PYTHONPATH python scripts/analyze_integrations.py --results results --paper /tmp/watchdelta-paper-data
	env -u PYTHONPATH python scripts/analyze_diagnostics.py --results results --paper /tmp/watchdelta-paper-data
	env -u PYTHONPATH python scripts/analyze_compound_scaling.py --results results --paper /tmp/watchdelta-paper-data
	env -u PYTHONPATH python scripts/analyze_panel.py --results results --dataset diagnostic-panel --paper /tmp/watchdelta-paper-data
	env -u PYTHONPATH python scripts/reference_audit.py --expected-count 67

verify: quickcheck analyze
	env -u PYTHONPATH python -m unittest discover -s tests -t . -v
	env -u PYTHONPATH python scripts/audit_completions.py

replay:
	bash scripts/reproduce.sh
