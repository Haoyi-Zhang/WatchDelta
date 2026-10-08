# WatchDelta artifact

WatchDelta qualifies a bounded edit-to-output episode by comparing a stable live projection with an isolated one-shot execution over identical terminal source bytes. When outputs disagree, it investigates six boundaries: selection, observation scope, state predicate, scheduling, consumer execution, and publication.

The implementation provides two complementary diagnostic modes:

1. an adaptive minimax planner that chooses repair interventions from the surviving candidate sets; and
2. a distance-constrained panel compiler that treats declared fault signatures as a codebook, solves a binary multicover problem, independently certifies minimum Hamming distance, and decodes only a unique hypothesis within the declared error budget.

For the evaluated 32-hypothesis model, the compiler produces a cardinality-five exact panel and a 12-execution panel with minimum distance three. The retained diagnostic-panel study contains 384 fresh-process executions. Its analyzer recomputes all 384 model signatures from episode records and retained output bytes, and enumerates all 1,920 single-observation substitutions.

## Evidence map

| Directory | Evidence |
|---|---|
| `results/primary-matrix` | 432 TypeScript and watchfiles/Markdown episodes |
| `results/sensitivity`, `timing-diagnostic`, `baseline-challenge`, `long-budget` | targeted controls and deadlines |
| `results/uvicorn-integration`, `hypercorn-integration` | fresh CLI integration processes |
| `results/boundary-diagnosis` | 48 single-boundary units, 84 executions |
| `results/compound-diagnosis` | 62 compound/unknown units, 206 executions |
| `results/diagnostic-panel` | 32 hypotheses × 12 interventions, 384 executions |
| `results/scaling-small`, `scaling-large` | 80 episodes across 10–5,000 files, overlay and tmpfs |
| `results/vite-filter-replay`, `mkdocs-batch-replay` | 72 versioned mechanism replays |
| `results/pilots/hypercorn-oracle-contamination` | excluded negative oracle pilot |

The complete evidence contains 1,300 actual-process executions and 72 mechanism replays. These heterogeneous layers are not pooled into a field failure rate.

## Environment and quick verification

```bash
python --version
node --version
npm --version
make quickcheck
make analyze
make verify
```

Direct script execution does not require an inherited `PYTHONPATH`. Runtime and Python package versions are pinned in `requirements-lock.txt`, `package.json`, and `evidence/installed-runtime-sha256.json`.

## Full replay

```bash
bash scripts/reproduce.sh /path/to/new-results
```

The replay is bounded, local, sequential, and refuses an existing destination. It uses open-source user-space tools and does not contact live services.

## Bibliography and result checks

```bash
python scripts/reference_audit.py --paper ../paper --expected-count 67
python scripts/audit_completions.py
```

Original code is available under the MIT license in `LICENSE`. Third-party source notices remain in `licenses/`. The public repository is [WatchDelta](https://github.com/Haoyi-Zhang/WatchDelta).

The retained study used Python 3.13.5 on Linux; its documentation CPU intervals include the HTTP probes and are not watcher-only overhead. Content-mode TypeScript runs use fresh one-shot compilation rather than the persistent watch compiler. The reproduction driver closes its CPU interval before HTTP retrieval. Unit tests can run on Windows, but actual-process replay requires Linux process groups and `/proc`.
