#!/usr/bin/env python3
"""Execute and audit distance-constrained diagnostic intervention panels."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import sys as _sys
from pathlib import Path as _BootstrapPath
_SRC = _BootstrapPath(__file__).resolve().parents[1] / "src"
if str(_SRC) not in _sys.path:
    _sys.path.insert(0, str(_SRC))

from watchdelta.active_diagnosis import (
    Hypothesis,
    SIGNATURES,
    hypothesis_space,
    predict_signature,
    record_signature,
    serialize_set,
)
from watchdelta.diagnostic_cases import case_for_hypothesis
from watchdelta.panel_diagnosis import (
    certify_panel,
    decode_nearest,
    exhaustive_single_corruptions,
    signature_vector,
    synthesize_panel,
)
from watchdelta.run import environment, episode


def build_protocol(settle_seconds: float = 1.0) -> dict[str, Any]:
    robust = synthesize_panel(1)
    # The no-error panel is optimized inside the already executed robust panel,
    # so both comparisons use the same actual-process records.
    exact = synthesize_panel(0, interventions=robust.panel)
    hypotheses = hypothesis_space()
    units = [
        {
            "id": f"panel-h{index:02d}",
            "truth": serialize_set(hypothesis),
            "numeric_base": 2_000_000 + index * 100,
        }
        for index, hypothesis in enumerate(hypotheses)
    ]
    return {
        "id": "distance-panel-study",
        "settle_seconds": settle_seconds,
        "hypothesis_count": len(hypotheses),
        "signature_alphabet": list(SIGNATURES) + ["unknown_stale"],
        "exact_panel": exact.as_dict(),
        "robust_panel": robust.as_dict(),
        "triple_repetition_runs": exact.selected_count * 3,
        "units": units,
    }


def run_unit(output: Path, unit: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    truth: Hypothesis = frozenset(unit["truth"])
    panel = tuple(frozenset(item) for item in protocol["robust_panel"]["panel"])
    steps: list[dict[str, Any]] = []
    observed: list[str] = []
    for step, repairs in enumerate(panel):
        case = case_for_hypothesis(
            unit_id=unit["id"],
            numeric_base=int(unit["numeric_base"]),
            truth=truth,
            repairs=repairs,
            step=step,
        )
        record = episode(output.resolve(), case, float(protocol["settle_seconds"]))
        actual = record_signature(record)
        predicted = predict_signature(truth, repairs)
        observed.append(actual)
        steps.append(
            {
                "step": step,
                "execution_id": case["id"],
                "repairs": serialize_set(repairs),
                "predicted": predicted,
                "observed": actual,
                "conformant": actual == predicted,
                "status": record.get("status"),
                "stable_latency_ms": record.get("stable_latency_ms"),
                "cpu_s": record.get("metrics", {}).get("cpu_s"),
            }
        )
    robust_decode = decode_nearest(observed, panel, 1)
    exact_panel = tuple(frozenset(item) for item in protocol["exact_panel"]["panel"])
    lookup = {repairs: observed[index] for index, repairs in enumerate(panel)}
    exact_observed = tuple(lookup[item] for item in exact_panel)
    exact_decode = decode_nearest(exact_observed, exact_panel, 0)
    return {
        "id": unit["id"],
        "truth": serialize_set(truth),
        "executions": len(steps),
        "model_conformant": all(step["conformant"] for step in steps),
        "exact_decode": exact_decode.as_dict(),
        "robust_decode": robust_decode.as_dict(),
        "steps": steps,
    }


def corruption_summary(protocol: dict[str, Any]) -> dict[str, Any]:
    alphabet = tuple(protocol["signature_alphabet"])
    hypotheses = hypothesis_space()
    result: dict[str, Any] = {}
    for name, budget in (("exact_panel", 0), ("robust_panel", 1)):
        panel = tuple(frozenset(item) for item in protocol[name]["panel"])
        counts = {"cases": 0, "recovered": 0, "false_exact": 0, "unresolved": 0, "unmodeled": 0}
        for truth in hypotheses:
            for transcript in exhaustive_single_corruptions(truth, panel, alphabet=alphabet):
                counts["cases"] += 1
                decoded = decode_nearest(transcript, panel, budget)
                if decoded.status == "exact" and decoded.hypothesis == truth:
                    counts["recovered"] += 1
                elif decoded.status == "exact":
                    counts["false_exact"] += 1
                else:
                    counts[decoded.status] += 1
        result[name] = counts
    return result


def summarize(records: list[dict[str, Any]], protocol: dict[str, Any]) -> dict[str, Any]:
    corruption = corruption_summary(protocol)
    exact_panel = tuple(frozenset(item) for item in protocol["exact_panel"]["panel"])
    robust_panel = tuple(frozenset(item) for item in protocol["robust_panel"]["panel"])
    # Independent certificate checks do not trust the serialized solver fields.
    exact_certificate = certify_panel(exact_panel, 0)
    robust_certificate = certify_panel(robust_panel, 1)
    return {
        "units": len(records),
        "planned_units": len(protocol["units"]),
        "actual_process_executions": sum(record["executions"] for record in records),
        "model_conformant_units": sum(record["model_conformant"] for record in records),
        "model_conformant_executions": sum(
            step["conformant"] for record in records for step in record["steps"]
        ),
        "exact_zero_error_recovered": sum(
            record["exact_decode"]["status"] == "exact"
            and record["exact_decode"]["hypothesis"] == record["truth"]
            for record in records
        ),
        "robust_zero_error_recovered": sum(
            record["robust_decode"]["status"] == "exact"
            and record["robust_decode"]["hypothesis"] == record["truth"]
            for record in records
        ),
        "exact_panel": exact_certificate.as_dict(),
        "robust_panel": robust_certificate.as_dict(),
        "greedy_reference_runs_including_baseline": 7,
        "triple_repetition_runs": int(protocol["triple_repetition_runs"]),
        "single_corruption": corruption,
        "completed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-units", type=int)
    args = parser.parse_args()

    if args.protocol:
        raw = args.protocol.read_bytes()
        protocol = json.loads(raw)
    else:
        protocol = build_protocol()
        raw = (json.dumps(protocol, indent=2, sort_keys=True) + "\n").encode()

    if args.output.exists():
        if not args.resume:
            raise SystemExit(f"Refusing existing output: {args.output}")
        if (args.output / "protocol.json").read_bytes() != raw:
            raise SystemExit("Resume protocol differs")
    else:
        args.output.mkdir(parents=True)
        (args.output / "protocol.json").write_bytes(raw)
        (args.output / "protocol.sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
        env = environment()
        env["panel_synthesis"] = {
            "exact": protocol["exact_panel"],
            "robust": protocol["robust_panel"],
        }
        (args.output / "environment.json").write_text(json.dumps(env, indent=2) + "\n")
        (args.output / "records.jsonl").write_text("")

    existing = [
        json.loads(line)
        for line in (args.output / "records.jsonl").read_text().splitlines()
        if line.strip()
    ]
    completed = {record["id"] for record in existing}
    pending = [unit for unit in protocol["units"] if unit["id"] not in completed]
    if args.max_units is not None:
        pending = pending[: args.max_units]

    with (args.output / "records.jsonl").open("a") as handle:
        for index, unit in enumerate(pending, 1):
            record = run_unit(args.output, unit, protocol)
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            print(
                f"{index}/{len(pending)} {unit['id']} "
                f"conformant={record['model_conformant']}",
                flush=True,
            )

    records = [
        json.loads(line)
        for line in (args.output / "records.jsonl").read_text().splitlines()
        if line.strip()
    ]
    summary = summarize(records, protocol)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    if len(records) == len(protocol["units"]):
        (args.output / "complete.json").write_text(
            json.dumps(
                {
                    "units": len(records),
                    "executions": summary["actual_process_executions"],
                    "completed_utc": summary["completed_utc"],
                },
                indent=2,
            )
            + "\n"
        )
    print(json.dumps(summary, indent=2))

    if len(records) == len(protocol["units"]):
        if summary["model_conformant_units"] != summary["units"]:
            raise SystemExit("An actual-process panel transcript diverged from the declared model")
        if summary["exact_zero_error_recovered"] != summary["units"]:
            raise SystemExit("The exact panel failed zero-error recovery")
        robust_cases = summary["single_corruption"]["robust_panel"]
        if robust_cases["recovered"] != robust_cases["cases"]:
            raise SystemExit("The robust panel failed a single-corruption case")
        if robust_cases["false_exact"] or robust_cases["unresolved"] or robust_cases["unmodeled"]:
            raise SystemExit("The robust panel produced a non-recovery result")


if __name__ == "__main__":
    main()
