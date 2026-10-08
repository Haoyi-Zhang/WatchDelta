#!/usr/bin/env bash
# Replay every declared dataset sequentially into a new destination.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
if [[ -x "$PWD/node_modules/.bin/tsc" ]]; then export WATCHDELTA_TSC="$PWD/node_modules/.bin/tsc"; fi
python scripts/preflight.py
DEST="${1:-results/replay-$(date -u +%Y%m%dT%H%M%SZ)}"
if [[ -e "$DEST" ]]; then echo "Refusing existing destination: $DEST" >&2; exit 2; fi
mkdir -p "$DEST"
python -m unittest discover -s tests -t . -v > "$DEST/unit-tests.txt" 2>&1
python -u -m watchdelta.run --protocol protocols/primary-matrix.json --output "$DEST/primary-matrix" | tee "$DEST/primary-matrix-console.txt"
python -u -m watchdelta.run --protocol protocols/sensitivity.json --output "$DEST/sensitivity" | tee "$DEST/sensitivity-console.txt"
python -u scripts/timing_diagnostic.py --protocol protocols/timing-diagnostic.json --output "$DEST/timing-diagnostic" | tee "$DEST/timing-console.txt"
python -u scripts/baseline_challenge.py --protocol protocols/baseline-challenge.json --output "$DEST/baseline-challenge" | tee "$DEST/baseline-console.txt"
python -u scripts/uvicorn_integration.py --protocol protocols/uvicorn-integration.json --output "$DEST/uvicorn-integration" | tee "$DEST/uvicorn-console.txt"
python -u scripts/long_budget.py --protocol protocols/long-budget.json --output "$DEST/long-budget" | tee "$DEST/long-budget-console.txt"
python -u scripts/hypercorn_integration.py --protocol protocols/hypercorn-integration.json --output "$DEST/hypercorn-integration" | tee "$DEST/hypercorn-console.txt"
python -u scripts/diagnosis_study.py --protocol protocols/boundary-diagnosis.json --output "$DEST/boundary-diagnosis" | tee "$DEST/boundary-diagnosis-console.txt"
python -u scripts/scaling_small.py --protocol protocols/scaling-small.json --output "$DEST/scaling-small" | tee "$DEST/scaling-small-console.txt"
python -u scripts/compound_diagnosis.py --protocol protocols/compound-diagnosis.json --output "$DEST/compound-diagnosis" | tee "$DEST/compound-diagnosis-console.txt"
python -u scripts/scaling_large.py --protocol protocols/scaling-large.json --output "$DEST/scaling-large" | tee "$DEST/scaling-large-console.txt"
python -u scripts/panel_study.py --protocol protocols/diagnostic-panel.json --output "$DEST/diagnostic-panel" | tee "$DEST/diagnostic-panel-console.txt"
node scripts/vite_filter_replay.mjs --output "$DEST/vite-filter-replay" | tee "$DEST/vite-filter-console.txt"
python -u scripts/mkdocs_batch_replay.py --output "$DEST/mkdocs-batch-replay" | tee "$DEST/mkdocs-batch-console.txt"
python scripts/analyze.py --results "$DEST" --paper "$DEST/paper-data" > "$DEST/analysis-primary.txt"
python scripts/analyze_integrations.py --results "$DEST" --paper "$DEST/paper-data" > "$DEST/analysis-integrations.txt"
python scripts/analyze_diagnostics.py --results "$DEST" --paper "$DEST/paper-data" > "$DEST/analysis-diagnostics.txt"
python scripts/analyze_compound_scaling.py --results "$DEST" --paper "$DEST/paper-data" > "$DEST/analysis-compound-scaling.txt"
python scripts/analyze_panel.py --results "$DEST" --dataset diagnostic-panel --paper "$DEST/paper-data" > "$DEST/analysis-panel.txt"
python scripts/audit_completions.py --results "$DEST" --output "$DEST/completion-field-audit.json" > "$DEST/completion-audit.txt"
python scripts/reference_audit.py --expected-count 67 > "$DEST/reference-audit.txt"
echo "Replay preserved in $DEST; compare complete obligations and mechanisms, not identical wall-clock samples."
