#!/usr/bin/env python3
"""Validate compound-diagnosis and large-tree scaling records and generate paper-ready artifacts.

This script intentionally recomputes every candidate-set transition from the
frozen protocol and per-episode records.  It also validates the compacted
1k/5k scaling records without relying on the removed duplicate trees.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any, Iterable


# Permit direct execution from an unpacked source tree without relying on an
# inherited PYTHONPATH.  Experiment semantics are unchanged.
import sys as _sys
from pathlib import Path as _BootstrapPath
_SRC = _BootstrapPath(__file__).resolve().parents[1] / "src"
if str(_SRC) not in _sys.path:
    _sys.path.insert(0, str(_SRC))
from watchdelta.active_diagnosis import (
    BOUNDARIES,
    choose_intervention,
    hypothesis_space,
    partition_sizes,
    record_signature,
    serialize_set,
    update_candidates,
)

ROOT = Path(__file__).resolve().parents[1]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n")


def median(values: Iterable[float]) -> float:
    data = list(values)
    if not data:
        raise RuntimeError("median of empty data")
    return float(statistics.median(data))


def fmt(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}"


def tex_escape(value: str) -> str:
    return value.replace("_", r"\_")


def validate_episode_record(record: dict[str, Any], folder: Path) -> None:
    expected = "matched" if record["observed_projection"] == record["clean"]["projection"] else "stale"
    if record.get("status") != expected:
        raise RuntimeError(f"status/projection mismatch: {record.get('id')}")
    if record["clean"].get("returncode") != 0:
        raise RuntimeError(f"clean oracle failed: {record.get('id')}")
    if record.get("snapshot_stable") is not True:
        raise RuntimeError(f"unstable endpoint snapshot: {record.get('id')}")
    if record.get("tool") == "docs" and record.get("served_matches_disk") is not True:
        raise RuntimeError(f"served/disk disagreement: {record.get('id')}")
    stored = json.loads((folder / "record.json").read_text())
    if stored != record:
        raise RuntimeError(f"record mirror differs: {record.get('id')}")


def validate_compound(results: Path, protocols: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    folder = results / "compound-diagnosis"
    protocol_raw = (folder / "protocol.json").read_bytes()
    protocol = json.loads(protocol_raw)
    if sha256_bytes(protocol_raw) != (folder / "protocol.sha256").read_text().strip():
        raise RuntimeError("compound protocol hash mismatch")
    if protocol_raw != (protocols / "compound-diagnosis.json").read_bytes():
        raise RuntimeError("compound protocol mirror mismatch")
    if (protocols / "compound-diagnosis.sha256").read_text().strip() != sha256_bytes(protocol_raw):
        raise RuntimeError("compound protocol mirror hash mismatch")

    records = read_jsonl(folder / "records.jsonl")
    planned = {unit["id"]: unit for unit in protocol["units"]}
    if collections.Counter(planned.keys()) != collections.Counter(record["id"] for record in records):
        raise RuntimeError("compound plan/records mismatch")
    if len(records) != 62:
        raise RuntimeError(f"expected 62 compound units, got {len(records)}")

    execution_count = 0
    for result in records:
        plan = planned[result["id"]]
        if result["truth"] != plan["truth"] or result["supported"] != plan["supported"]:
            raise RuntimeError(f"compound truth/support changed: {result['id']}")
        candidates = hypothesis_space()
        used: list[frozenset[str]] = []
        supported_truth = frozenset(value for value in plan["truth"] if value in BOUNDARIES)
        for index, step in enumerate(result["trace"]):
            repairs = frozenset(step["repairs"])
            if index == 0 and repairs:
                raise RuntimeError(f"compound first repair is not empty: {result['id']}")
            if index > 0:
                expected_repairs = choose_intervention(candidates, used)
                if repairs != expected_repairs:
                    raise RuntimeError(f"planner trace differs: {result['id']} step {index}")
            before = candidates
            execution = json.loads((folder / "episodes" / step["execution_id"] / "record.json").read_text())
            validate_episode_record(execution, folder / "episodes" / step["execution_id"])
            observed = record_signature(execution)
            if observed != step["observed"]:
                raise RuntimeError(f"observed signature changed: {result['id']} step {index}")
            if partition_sizes(before, repairs) != step["predicted_partition"]:
                raise RuntimeError(f"partition changed: {result['id']} step {index}")
            candidates = update_candidates(before, repairs, observed)
            if step["candidates_before"] != len(before) or step["candidates_after"] != len(candidates):
                raise RuntimeError(f"candidate cardinality changed: {result['id']} step {index}")
            if step["candidate_sets"] != [serialize_set(item) for item in candidates]:
                raise RuntimeError(f"candidate list changed: {result['id']} step {index}")
            if result["supported"] and step["truth_retained"] != (supported_truth in candidates):
                raise RuntimeError(f"truth-retention flag changed: {result['id']} step {index}")
            used.append(repairs)
            execution_count += 1
        if result["final_candidates"] != [serialize_set(item) for item in candidates]:
            raise RuntimeError(f"final candidate list changed: {result['id']}")
        if result["supported"]:
            if result["outcome"] != "exact" or candidates != (supported_truth,):
                raise RuntimeError(f"modeled compound not exactly recovered: {result['id']}")
        else:
            if result["outcome"] != "unmodeled" or candidates:
                raise RuntimeError(f"unknown compound was not rejected: {result['id']}")

    summary = json.loads((folder / "summary.json").read_text())
    if summary["actual_process_executions"] != execution_count:
        raise RuntimeError("compound execution count mismatch")
    if summary["known_exact"] != 50 or summary["unknown_unmodeled"] != 12:
        raise RuntimeError("compound outcome summary mismatch")
    complete = json.loads((folder / "complete.json").read_text())
    if complete["units"] != 62 or complete["executions"] != execution_count:
        raise RuntimeError("compound completion marker mismatch")
    return records, summary


def validate_scaling_large(results: Path, protocols: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    folder = results / "scaling-large"
    protocol_raw = (folder / "protocol.json").read_bytes()
    protocol = json.loads(protocol_raw)
    if sha256_bytes(protocol_raw) != (folder / "protocol.sha256").read_text().strip():
        raise RuntimeError("scaling-large protocol hash mismatch")
    if protocol_raw != (protocols / "scaling-large.json").read_bytes():
        raise RuntimeError("scaling-large protocol mirror mismatch")
    if (protocols / "scaling-large.sha256").read_text().strip() != sha256_bytes(protocol_raw):
        raise RuntimeError("scaling-large protocol mirror hash mismatch")

    records = read_jsonl(folder / "records.jsonl")
    planned = {job["id"]: job for job in protocol["jobs"]}
    if collections.Counter(planned.keys()) != collections.Counter(record["id"] for record in records):
        raise RuntimeError("scaling-large plan/records mismatch")
    if len(records) != 32:
        raise RuntimeError(f"expected 32 scaling-large records, got {len(records)}")
    environment = json.loads((folder / "environment.json").read_text())
    if environment["mounts"]["overlay"]["fstype"] != "overlay":
        raise RuntimeError("overlay provenance mismatch")
    if environment["mounts"]["tmpfs"]["fstype"] != "tmpfs":
        raise RuntimeError("tmpfs provenance mismatch")

    for record in records:
        plan = planned[record["id"]]
        for key, value in plan.items():
            if record.get(key) != value:
                raise RuntimeError(f"scaling-large frozen attribute changed: {record['id']} {key}")
        episode_folder = folder / "episodes" / record["id"]
        stored = json.loads((episode_folder / "record.json").read_text())
        if stored != record:
            raise RuntimeError(f"scaling-large record mirror differs: {record['id']}")
        if record["status"] != "matched":
            raise RuntimeError(f"scaling-large mismatch: {record['id']}")
        if record["clean"]["returncode"] != 0 or record.get("snapshot_stable") is not True:
            raise RuntimeError(f"scaling-large invalid endpoint: {record['id']}")
        if record["tool"] == "docs" and record.get("served_matches_disk") is not True:
            raise RuntimeError(f"scaling-large served/disk disagreement: {record['id']}")
        manifest = json.loads((episode_folder / "retained-manifest.json").read_text())
        if manifest["source_files"] != record["file_count"]:
            raise RuntimeError(f"scaling-large source count mismatch: {record['id']}")
        if manifest["source_sha256"] != record["clean"]["source_sha256"]:
            raise RuntimeError(f"scaling-large source hash mismatch: {record['id']}")
        observed_hash = sha256_bytes(json.dumps(record["observed_projection"], sort_keys=True).encode())
        clean_hash = sha256_bytes(json.dumps(record["clean"]["projection"], sort_keys=True).encode())
        if manifest["observed_projection_sha256"] != observed_hash:
            raise RuntimeError(f"scaling-large observed projection hash mismatch: {record['id']}")
        if manifest["clean_projection_sha256"] != clean_hash:
            raise RuntimeError(f"scaling-large clean projection hash mismatch: {record['id']}")
        for compacted in manifest["compacted_paths"]:
            if (episode_folder / compacted).exists():
                raise RuntimeError(f"scaling-large uncompacted duplicate tree: {record['id']} {compacted}")
        samples = list((episode_folder / "retained-samples").rglob("*"))
        if not any(path.is_file() for path in samples):
            raise RuntimeError(f"scaling-large missing retained samples: {record['id']}")

    summary = json.loads((folder / "summary.json").read_text())
    if summary["episodes"] != 32 or summary["matched"] != 32 or summary["stale"] != 0:
        raise RuntimeError("scaling-large summary mismatch")
    complete = json.loads((folder / "complete.json").read_text())
    if complete["episodes"] != 32:
        raise RuntimeError("scaling-large completion marker mismatch")
    return records, summary


def load_scaling_small(results: Path) -> list[dict[str, Any]]:
    records = read_jsonl(results / "scaling-small" / "records.jsonl")
    if len(records) != 48 or any(record["status"] != "matched" for record in records):
        raise RuntimeError("scaling-small prerequisite is incomplete")
    return records


def aggregate_scaling(records_small: list[dict[str, Any]], records_large: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = records_small + records_large
    rows: list[dict[str, Any]] = []
    for tool, mode in (("tsc", "default"), ("tsc", "hash"), ("docs", "relevant"), ("docs", "hash")):
        for size in (10, 250, 1000, 5000):
            selected = [
                record
                for record in records
                if record["tool"] == tool and record["mode"] == mode and record["file_count"] == size
            ]
            if not selected:
                raise RuntimeError(f"missing scaling cell {tool}/{mode}/{size}")
            rows.append(
                {
                    "tool": tool,
                    "mode": mode,
                    "file_count": size,
                    "n": len(selected),
                    "matched": sum(record["status"] == "matched" for record in selected),
                    "latency_median_ms": median(
                        record["stable_latency_ms"]
                        for record in selected
                        if record.get("stable_latency_ms") is not None
                    ),
                    "cpu_median_ms": median(record["metrics"]["cpu_s"] * 1000 for record in selected),
                    "scan_median_kib": median(record["metrics"]["scan_bytes"] / 1024 for record in selected),
                    "ready_median_ms": median(
                        record.get("setup_to_ready_ms", 0.0) for record in selected
                    )
                    if size >= 1000
                    else None,
                }
            )
    return rows


def render_outputs(
    paper: Path,
    results: Path,
    compound_records: list[dict[str, Any]],
    compound_summary: dict[str, Any],
    scaling_large_summary: dict[str, Any],
    scaling_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    known = [record for record in compound_records if record["supported"]]
    unknown = [record for record in compound_records if not record["supported"]]
    groups = []
    for width in (2, 3, 4):
        selected = [record for record in known if len(record["truth"]) == width]
        groups.append(
            {
                "label": {2: "Two-boundary", 3: "Three-boundary", 4: "Four-boundary"}[width],
                "units": len(selected),
                "outcome": f"{sum(record['outcome'] == 'exact' for record in selected)}/{len(selected)} exact",
                "median": median(record["executions"] for record in selected),
                "range": f"{min(record['executions'] for record in selected)}--{max(record['executions'] for record in selected)}",
            }
        )
    compound_rows = [
        f"{group['label']} & {group['units']} & {group['outcome']} & {group['median']:.1f} & {group['range']} \\\\"
        for group in groups
    ]
    compound_rows.append(
        f"Out-of-model corruption & {len(unknown)} & {sum(record['outcome'] == 'unmodeled' for record in unknown)}/{len(unknown)} unmodeled & {median(record['executions'] for record in unknown):.1f} & {min(record['executions'] for record in unknown)}--{max(record['executions'] for record in unknown)} \\\\"
    )
    write(
        paper / "generated/compound.tex",
        r"""\begin{table*}[t]
\centering
\caption{Frozen compound-fault holdout. Each unit is repeated twice; ``exact'' means the final candidate set equals the injected modeled set. Out-of-model corruption must empty the candidate set rather than receive a known label.}
\label{tab:compound}
\begin{tabular}{lrrcc}\toprule
Fault set & Units & Outcome & Median runs & Range\\\midrule
"""
        + "\n".join(compound_rows)
        + r"""
\bottomrule\end{tabular}
\end{table*}""",
    )

    # One compact table reports endpoints and cost growth; the plot carries the full curves.
    scale_table_rows = []
    names = {
        ("tsc", "default"): "TypeScript/native",
        ("tsc", "hash"): "TypeScript/content",
        ("docs", "relevant"): "Docs/relevant",
        ("docs", "hash"): "Docs/content",
    }
    for key, label in names.items():
        row_10 = next(row for row in scaling_rows if (row["tool"], row["mode"]) == key and row["file_count"] == 10)
        row_5000 = next(row for row in scaling_rows if (row["tool"], row["mode"]) == key and row["file_count"] == 5000)
        scale_table_rows.append(
            f"{label} & {row_10['matched']}/{row_10['n']} & {row_5000['matched']}/{row_5000['n']} & "
            f"{fmt(row_10['latency_median_ms'])} $\\rightarrow$ {fmt(row_5000['latency_median_ms'])} & "
            f"{fmt(row_10['cpu_median_ms'])} $\\rightarrow$ {fmt(row_5000['cpu_median_ms'])} & "
            f"{fmt(row_10['scan_median_kib'])} $\\rightarrow$ {fmt(row_5000['scan_median_kib'])} \\\\"
        )
    write(
        paper / "generated/scaling-large.tex",
        r"""\begin{table*}[t]
\centering
\caption{Scaling endpoints and median post-readiness costs, shown as 10 $\rightarrow$ 5,000 source files. The 10-file cells have six runs; 5,000-file cells have four runs pooled across overlay and tmpfs. Scanned KiB excludes ordinary consumer reads.}
\label{tab:scaling-large}
\begin{tabular}{lrrrrr}\toprule
Path & Match (10) & Match (5k) & Latency ms & CPU ms & Scanned KiB\\\midrule
"""
        + "\n".join(scale_table_rows)
        + r"""
\bottomrule\end{tabular}
\end{table*}""",
    )

    # Data files consumed by the PGFPlots figure.
    labels = list(names.items())
    latency_header = "files " + " ".join(f"s{index}" for index in range(len(labels)))
    cpu_header = latency_header
    latency_lines = [latency_header]
    cpu_lines = [cpu_header]
    for size in (10, 250, 1000, 5000):
        latency_values = []
        cpu_values = []
        for key, _label in labels:
            row = next(row for row in scaling_rows if (row["tool"], row["mode"]) == key and row["file_count"] == size)
            latency_values.append(f"{row['latency_median_ms']:.6f}")
            cpu_values.append(f"{row['cpu_median_ms']:.6f}")
        latency_lines.append(str(size) + " " + " ".join(latency_values))
        cpu_lines.append(str(size) + " " + " ".join(cpu_values))
    write(paper / "generated/scaling-latency.dat", "\n".join(latency_lines))
    write(paper / "generated/scaling-cpu.dat", "\n".join(cpu_lines))

    runtime_before_compound = json.loads((results / "derived/diagnostics-summary.json").read_text())["runtime_total"]
    replay_count = json.loads((results / "derived/extensions-summary.json").read_text())["vite"]["cases"] + json.loads((results / "derived/extensions-summary.json").read_text())["mkdocs"]["episodes"]
    runtime_total = runtime_before_compound + compound_summary["actual_process_executions"] + scaling_large_summary["episodes"]
    all_cases = runtime_total + replay_count
    fixed_panel_breadth = 17
    macros = {
        "CompoundUnitN": compound_summary["units"],
        "CompoundKnownN": compound_summary["known_units"],
        "CompoundExactN": compound_summary["known_exact"],
        "CompoundUnknownN": compound_summary["unknown_units"],
        "CompoundUnmodeledN": compound_summary["unknown_unmodeled"],
        "CompoundExecutionN": compound_summary["actual_process_executions"],
        "CompoundMedianSteps": str(compound_summary["episodes_known_median"]),
        "CompoundMaxSteps": compound_summary["episodes_known_max"],
        "FixedPanelN": compound_summary["fixed_panel_size"],
        "FixedPanelBreadthN": fixed_panel_breadth,
        "ScaleLargeN": scaling_large_summary["episodes"],
        "ScaleLargeMatchedN": scaling_large_summary["matched"],
        "ScaleAllN": 48 + scaling_large_summary["episodes"],
        "ScaleAllMatchedN": 48 + scaling_large_summary["matched"],
        "MaxTreeN": 5000,
        "CompoundRuntimeEpisodeN": runtime_total,
        "CompoundAllEvidenceN": all_cases,
    }
    write(
        paper / "generated/numbers-compound.tex",
        "% Generated from validated compound-diagnosis and scaling records.\n"
        + "\n".join(f"\\newcommand{{\\{key}}}{{{value}}}" for key, value in macros.items()),
    )

    evidence_text = r"""\begin{table*}[t]
\centering
\caption{Evidence layers. Runtime episodes, controlled mutations, and source-level replays answer different questions and are not pooled into a field failure rate.}
\label{tab:evidence}
\begin{tabular}{p{0.17\textwidth}p{0.27\textwidth}rp{0.37\textwidth}}\toprule
Layer & Systems and protocol & Runs & Evidence provided\\\midrule
Ordinary runtime matrix & TypeScript watch; watchfiles/Markdown/HTTP & 432 & Default and existing configurations across eight edit programs; terminal output versus isolated execution.\\
Runtime integrations and diagnostics & Timing, strong baseline, Uvicorn, Hypercorn, sensitivity & 114 & Independent CLIs, longer deadlines, predicate controls, and deliberately injected failures.\\
Single-boundary calibration & Eight seeded classes & 84 & Checks that each observable signature and repair intervention behaves as declared.\\
Compound active diagnosis & Two--four modeled boundaries; one unknown mechanism & __COMPOUND_RUNS__ & __KNOWN_UNITS__ modeled units recovered exactly; __UNKNOWN_UNITS__ unknown units rejected as unmodeled.\\
Tree/filesystem holdouts & 10--5,000 files; overlay/tmpfs & 80 & Terminal agreement plus response, CPU, scan work, and startup cost under native/relevant and content modes.\\
Versioned mechanism replays & Vite tagged decision; merged MkDocs loop & 72 & Exact declared source boundary, not full historical application runtime.\\
\bottomrule\end{tabular}
\end{table*}"""
    evidence_text = (
        evidence_text.replace("__COMPOUND_RUNS__", str(compound_summary["actual_process_executions"]))
        .replace("__KNOWN_UNITS__", str(compound_summary["known_units"]))
        .replace("__UNKNOWN_UNITS__", str(compound_summary["unknown_units"]))
    )
    write(paper / "generated/evidence.tex", evidence_text)

    derived = {
        "compound": compound_summary,
        "compound_by_width": groups,
        "scaling_large": scaling_large_summary,
        "scaling_all": scaling_rows,
        "runtime_total": runtime_total,
        "mechanism_replays": replay_count,
        "all_executed_cases": all_cases,
        "macros": macros,
    }
    write(results / "derived/compound-scaling-summary.json", json.dumps(derived, indent=2))
    write(results / "analysis-complete.json", json.dumps(derived, indent=2))
    return derived


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    parser.add_argument("--paper", type=Path, required=True)
    args = parser.parse_args()
    compound_records, compound_summary = validate_compound(args.results, ROOT / "protocols")
    scaling_large_records, scaling_large_summary = validate_scaling_large(args.results, ROOT / "protocols")
    scaling_rows = aggregate_scaling(load_scaling_small(args.results), scaling_large_records)
    derived = render_outputs(
        args.paper,
        args.results,
        compound_records,
        compound_summary,
        scaling_large_summary,
        scaling_rows,
    )
    print(json.dumps(derived, indent=2))


if __name__ == "__main__":
    main()
