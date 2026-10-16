# WatchDelta artifact

WatchDelta qualifies a bounded edit-to-output episode by comparing a stable live projection with an isolated one-shot execution over identical terminal source bytes. When outputs disagree, it investigates six boundaries: selection, observation scope, state predicate, scheduling, consumer execution, and publication.

The implementation provides two complementary diagnostic modes:

1. an adaptive minimax planner that chooses repair interventions from the surviving candidate sets; and
2. a distance-constrained panel compiler that treats declared fault signatures as a codebook, solves a binary multicover problem, independently certifies minimum Hamming distance, and decodes only a unique hypothesis within the declared error budget.

For the evaluated 32-hypothesis model, the compiler produces a cardinality-five exact panel and a 12-execution panel with minimum distance three. The retained diagnostic-panel study contains 384 fresh-process executions. Its analyzer recomputes all 384 model signatures from episode records and retained output bytes, and enumerates all 1,920 single-observation substitutions.

The main mutation execution adapter receives injected truth and constructs each fresh replay with the named faults omitted. The planner itself never receives truth. This is oracle-driven repair simulation, not a general unknown-workflow repair adapter. Qualification is mandatory before diagnosis: a failed reference, invalid readiness order, or unstable snapshot is inconclusive; an output or consumer disagreement is nonconforming. The panel decoder cannot hide inconclusive episodes inside its signature-error budget. An analyzer error blocks generation of manuscript success tables.

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

The retained Linux study contains 1,300 actual-process executions and 72 mechanism replays. These heterogeneous layers are not pooled into a field failure rate.

`results/local-unknown-bytes` is a separate 24-process Windows comparison using the standard-library one-file observer in `scripts/local_unknown.py`. The repair routine changes actual selector/scope configuration on the running process without a truth lookup. Unchanged/manual/configured strategies reach 0/8, 8/8, and 8/8 current endpoints; their next-edit endpoints are 0/8, 0/8, and 8/8. Median intervention wall times are 0.125, 0.482, and 204.488 ms, with the last including a fixed 200-ms decision probe. CPU deltas are below the observed process-clock resolution. `results/local-unknown` retains an excluded preliminary run with a newline-normalizing comparator; it is not watcher-failure evidence and is not in these denominators.

Run this small comparison without the Linux-only replay dependencies:

```bash
python scripts/local_unknown.py --output results/local-new-run --repetitions 4
python -m pytest -q tests/test_qualification.py tests/test_local_unknown.py
```

## Environment and quick verification

Run from this artifact directory. The full verification commands below target
the recorded Linux environment (CPython 3.13.5, Node.js 22.16.0 and TypeScript
5.8.3) and use POSIX `make`/`env`; they are not a Windows full-replay recipe.
Install the pinned Python dependencies and local TypeScript first:

```bash
python -m pip install -r requirements-lock.txt
npm install --ignore-scripts --no-audit --no-fund
export WATCHDELTA_TSC="$PWD/node_modules/typescript/lib/tsc.js"
```

The runner passes this TypeScript source path to Node; a global `tsc` is not
required. Then verify:

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

## Render retained scaling observations

The workflow and diagnostic-panel diagrams are direct Matplotlib vectors with
embedded fonts. The full bundle's `paper/build.py` regenerates both:

```sh
python plots/draw_schematics.py --output-dir ../paper/figures
```

Install `requirements-figures.txt`, then run
`python scripts/render_scaling.py --source plot_inputs --output-dir figures --font-root /path/to/texmf-dist/fonts`.
The optional vector renderer preserves both log-scale panels, all four series
and the observed nonmonotone values. It reads the retained episode medians;
it does not start watchers or replace actual-process measurements. Its five
input and routing checks are included in the ordinary test suite.
