#!/usr/bin/env python3
"""Validate the distance-constrained panel study and generate paper inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

import sys as _sys
from pathlib import Path as _BootstrapPath
_SRC = _BootstrapPath(__file__).resolve().parents[1] / "src"
if str(_SRC) not in _sys.path:
    _sys.path.insert(0, str(_SRC))

from watchdelta.active_diagnosis import hypothesis_space, predict_signature, record_signature
from watchdelta.panel_diagnosis import certify_panel, decode_nearest, exhaustive_single_corruptions
from watchdelta.core import projection


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def macro(name: str, value: object) -> str:
    return f"\\newcommand{{\\{name}}}{{{value}}}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=Path("results"))
    parser.add_argument("--paper", type=Path)
    parser.add_argument("--dataset", default="diagnostic-panel")
    args = parser.parse_args()

    root = args.results / args.dataset
    errors: list[str] = []
    for name in ("protocol.json", "protocol.sha256", "records.jsonl", "summary.json", "complete.json"):
        check((root / name).is_file(), f"missing {root / name}", errors)
    if errors:
        print(json.dumps({"errors": errors}, indent=2))
        return 1

    protocol = read_json(root / "protocol.json")
    records = read_jsonl(root / "records.jsonl")
    stored_summary = read_json(root / "summary.json")
    protocol_hash = (root / "protocol.sha256").read_text().strip()
    check(protocol_hash == sha256(root / "protocol.json"), "protocol hash mismatch", errors)

    hypotheses = hypothesis_space()
    truth_map = {tuple(unit["truth"]): unit for unit in protocol["units"]}
    check(len(hypotheses) == 32, "unexpected hypothesis-space size", errors)
    check(len(protocol["units"]) == 32, "protocol does not contain 32 units", errors)
    check(len(records) == len(protocol["units"]), "record count differs from protocol", errors)
    check(len({record["id"] for record in records}) == len(records), "duplicate record IDs", errors)

    robust_panel = tuple(frozenset(item) for item in protocol["robust_panel"]["panel"])
    exact_panel = tuple(frozenset(item) for item in protocol["exact_panel"]["panel"])
    robust_certificate = certify_panel(robust_panel, 1)
    exact_certificate = certify_panel(exact_panel, 0)
    check(exact_certificate.selected_count == 5, "exact panel is not cardinality five", errors)
    check(exact_certificate.minimum_distance == 1, "exact panel minimum distance is not one", errors)
    check(robust_certificate.selected_count == 12, "robust panel is not cardinality twelve", errors)
    check(robust_certificate.minimum_distance == 3, "robust panel minimum distance is not three", errors)
    check(set(exact_panel).issubset(set(robust_panel)), "exact panel is not nested in robust panel", errors)

    all_steps: list[dict[str, Any]] = []
    exact_recovered = 0
    robust_recovered = 0
    for record in records:
        truth_tuple = tuple(record["truth"])
        check(truth_tuple in truth_map, f"unknown truth in {record['id']}", errors)
        truth = frozenset(record["truth"])
        check(len(record["steps"]) == len(robust_panel), f"wrong step count in {record['id']}", errors)
        observed_by_repairs: dict[frozenset[str], str] = {}
        for step, repairs in zip(record["steps"], robust_panel, strict=True):
            step_repairs = frozenset(step["repairs"])
            check(step_repairs == repairs, f"panel order mismatch in {record['id']}", errors)
            predicted = predict_signature(truth, repairs)
            episode_file = root / 'episodes' / step['execution_id'] / 'record.json'
            episode = read_json(episode_file)
            check(projection(episode_file.parent / 'observed', '.html') == episode['observed_projection'],
                  f"retained observed bytes mismatch in {step['execution_id']}", errors)
            check(projection(episode_file.parent / 'clean/out', '.html') == episode['clean']['projection'],
                  f"retained clean bytes mismatch in {step['execution_id']}", errors)
            observed = record_signature(episode)
            check(step['observed'] == observed, f"episode signature mismatch in {step['execution_id']}", errors)
            check(step["predicted"] == predicted, f"stored prediction mismatch in {record['id']}", errors)
            check(observed == predicted, f"actual/model mismatch in {record['id']}", errors)
            check(step["conformant"] is (observed == predicted), f"conformance flag mismatch in {record['id']}", errors)
            observed_by_repairs[repairs] = observed
            all_steps.append(step)
        robust_observed = tuple(observed_by_repairs[item] for item in robust_panel)
        exact_observed = tuple(observed_by_repairs[item] for item in exact_panel)
        robust_decoded = decode_nearest(robust_observed, robust_panel, 1)
        exact_decoded = decode_nearest(exact_observed, exact_panel, 0)
        if robust_decoded.status == "exact" and robust_decoded.hypothesis == truth:
            robust_recovered += 1
        if exact_decoded.status == "exact" and exact_decoded.hypothesis == truth:
            exact_recovered += 1
        check(record["robust_decode"] == robust_decoded.as_dict(), f"robust decode mismatch in {record['id']}", errors)
        check(record["exact_decode"] == exact_decoded.as_dict(), f"exact decode mismatch in {record['id']}", errors)

    corruption = {}
    for label, panel, budget in [('robust_panel', robust_panel, 1), ('exact_panel', exact_panel, 0)]:
        counts = dict(cases=0, recovered=0, false_exact=0, unresolved=0, unmodeled=0)
        for truth in hypotheses:
            for transcript in exhaustive_single_corruptions(truth, panel):
                counts['cases'] += 1
                decoded = decode_nearest(transcript, panel, budget)
                if decoded.status == 'exact':
                    counts['recovered' if decoded.hypothesis == truth else 'false_exact'] += 1
                elif decoded.status == 'unmodeled':
                    counts['unmodeled'] += 1
                else:
                    counts['unresolved'] += 1
        corruption[label] = counts
        check(counts == stored_summary['single_corruption'][label], f"corruption replay mismatch for {label}", errors)
    robust_corrupt = corruption["robust_panel"]
    exact_corrupt = corruption["exact_panel"]
    check(robust_corrupt["cases"] == 1920, "robust corruption denominator is not 1920", errors)
    check(robust_corrupt["recovered"] == robust_corrupt["cases"], "robust panel did not recover every corruption", errors)
    check(robust_corrupt["false_exact"] == 0, "robust panel made a false exact attribution", errors)
    check(robust_corrupt["unresolved"] == 0, "robust panel left a single corruption unresolved", errors)
    check(robust_corrupt["unmodeled"] == 0, "robust panel rejected a correctable corruption", errors)

    recomputed = {
        "units": len(records),
        "actual_process_executions": len(all_steps),
        "model_conformant_units": sum(all(step["conformant"] for step in record["steps"]) for record in records),
        "model_conformant_executions": sum(bool(step["conformant"]) for step in all_steps),
        "exact_zero_error_recovered": exact_recovered,
        "robust_zero_error_recovered": robust_recovered,
        "exact_panel": exact_certificate.as_dict(),
        "robust_panel": robust_certificate.as_dict(),
        "robust_single_corruption": robust_corrupt,
        "exact_single_corruption": exact_corrupt,
        "median_stable_latency_ms": round(statistics.median(float(step["stable_latency_ms"]) for step in all_steps if step["stable_latency_ms"] is not None), 1),
        "median_worker_cpu_ms": round(1000 * statistics.median(float(step["cpu_s"]) for step in all_steps if step["cpu_s"] is not None), 1),
    }
    check(recomputed["actual_process_executions"] == 384, "panel study does not contain 384 executions", errors)
    check(recomputed["model_conformant_executions"] == recomputed["actual_process_executions"], "one or more panel executions diverged from the model", errors)
    check(exact_recovered == len(records), "exact panel failed a zero-error unit", errors)
    check(robust_recovered == len(records), "robust panel failed a zero-error unit", errors)

    for key in ("units", "actual_process_executions", "model_conformant_units", "model_conformant_executions", "exact_zero_error_recovered", "robust_zero_error_recovered"):
        check(stored_summary.get(key) == recomputed[key], f"stored summary mismatch for {key}", errors)

    output = {
        "dataset": args.dataset,
        "protocol_sha256": protocol_hash,
        "recomputed": recomputed,
        "solver_exact": protocol["exact_panel"],
        "solver_robust": protocol["robust_panel"],
        "errors": errors,
    }

    if args.paper is not None:
        generated = args.paper / "generated"
        generated.mkdir(parents=True, exist_ok=True)
        macros = [
            "% Generated from validated diagnostic-panel records.",
            macro("PanelUnitN", len(records)),
            macro("PanelExecutionN", len(all_steps)),
            macro("PanelConformantN", recomputed["model_conformant_executions"]),
            macro("ExactPanelRunN", exact_certificate.selected_count),
            macro("ExactPanelDistanceN", exact_certificate.minimum_distance),
            macro("RobustPanelRunN", robust_certificate.selected_count),
            macro("RobustPanelDistanceN", robust_certificate.minimum_distance),
            macro("RobustPanelCorruptionN", robust_corrupt["cases"]),
            macro("RobustPanelRecoveredN", robust_corrupt["recovered"]),
            macro("ExactPanelFalseN", exact_corrupt["false_exact"]),
            macro("TripleRepeatRunN", protocol["triple_repetition_runs"]),
            macro("PanelMedianLatencyMs", recomputed["median_stable_latency_ms"]),
            macro("PanelMedianCpuMs", recomputed["median_worker_cpu_ms"]),
            macro("RuntimeExecutionN", 916 + len(all_steps)),
            macro("TotalEvidenceN", 916 + len(all_steps) + 72),
        ]
        (generated / "numbers-panel.tex").write_text("\n".join(macros) + "\n", encoding="utf-8")
        compound_path = args.results / "analysis-complete.json"
        if not compound_path.is_file():
            errors.append(f"missing compound analysis for manuscript table: {compound_path}")
        else:
            compound = read_json(compound_path)
            by_width = {row["label"]: row for row in compound["compound_by_width"]}
            unknown = compound["compound"]
            row_end = " " + "\\\\"
            table_lines = [
                r"\begin{table*}[t]",
                r"\centering",
        r"\caption{Diagnosis results. Compound units are repeated twice. Panel runs include the unrepaired baseline; $d_{\min}$ is recomputed from the codebook.}",
                r"\label{tab:diagnosis}",
                r"\scriptsize",
                r"\setlength{\tabcolsep}{4.5pt}",
                r"\begin{tabular}{llrrrrl}",
                r"\toprule",
                r"Mode & Condition & Units/transcripts & Runs & $d_{\min}$ & Correct result & Outcome" + row_end,
                r"\midrule",
                f"Adaptive & Two-boundary faults & {by_width['Two-boundary']['units']} & {by_width['Two-boundary']['range']} & -- & {by_width['Two-boundary']['units']} & exact set" + row_end,
                f"Adaptive & Three-boundary faults & {by_width['Three-boundary']['units']} & {by_width['Three-boundary']['range']} & -- & {by_width['Three-boundary']['units']} & exact set" + row_end,
                f"Adaptive & Four-boundary faults & {by_width['Four-boundary']['units']} & {by_width['Four-boundary']['range']} & -- & {by_width['Four-boundary']['units']} & exact set" + row_end,
                f"Adaptive & Unknown corruption & {unknown['unknown_units']} & 1--3 & -- & {unknown['unknown_unmodeled']} & unmodeled" + row_end,
                r"\midrule",
                f"Model-only & Greedy separating panel & {len(records)} & 7 & 1 & -- & separating codebook" + row_end,
                f"Compiled & Exact panel & {len(records)} & {exact_certificate.selected_count} & {exact_certificate.minimum_distance} & {exact_recovered} & exact, no noise" + row_end,
                f"Compiled & Robust panel & {len(records)} & {robust_certificate.selected_count} & {robust_certificate.minimum_distance} & {robust_recovered} & exact, no noise" + row_end,
                f"Compiled & Robust + one substitution & {robust_corrupt['cases']:,} & {robust_certificate.selected_count} & {robust_certificate.minimum_distance} & {robust_corrupt['recovered']:,} & corrected" + row_end,
                r"\bottomrule",
                r"\end{tabular}",
                r"\end{table*}",
            ]
            table = "\n".join(table_lines) + "\n"
            (generated / "diagnosis.tex").write_text(table, encoding="utf-8")

    print(json.dumps(output, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
