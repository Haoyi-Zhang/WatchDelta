#!/usr/bin/env python3
"""Run a frozen compound-fault, active-diagnosis holdout.

The planner receives only observable episode signatures.  Ground-truth fault
sets are used by the mutation harness to construct each fresh process, then are
withheld from intervention selection.  Known combinations test exact recovery;
post-build corruption is deliberately outside the model and must remain
unmodeled rather than receiving a convenient boundary label.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path
from typing import Any


# Permit direct execution from an unpacked source tree without relying on an
# inherited PYTHONPATH.  Experiment semantics are unchanged.
import sys as _sys
from pathlib import Path as _BootstrapPath
_SRC = _BootstrapPath(__file__).resolve().parents[1] / "src"
if str(_SRC) not in _sys.path:
    _sys.path.insert(0, str(_SRC))
from watchdelta.active_diagnosis import (
    BOUNDARIES,
    DOWNSTREAM_BOUNDARIES,
    Hypothesis,
    Intervention,
    choose_intervention,
    greedy_separating_panel,
    hypothesis_space,
    partition_sizes,
    record_signature,
    serialize_set,
    update_candidates,
)
from watchdelta.run import environment, episode
from watchdelta.diagnostic_cases import UNKNOWN_FAULT, case_for_hypothesis

KNOWN_COMBINATIONS: tuple[tuple[str, ...], ...] = tuple(
    tuple(serialize_set(hypothesis))
    for hypothesis in hypothesis_space()
    if len(hypothesis) >= 2
)
UNKNOWN_COMBINATIONS: tuple[tuple[str, ...], ...] = (
    (UNKNOWN_FAULT,),
    ("selection", UNKNOWN_FAULT),
    ("observation_scope", UNKNOWN_FAULT),
    ("state_predicate", UNKNOWN_FAULT),
    ("scheduling", UNKNOWN_FAULT),
    ("consumer", UNKNOWN_FAULT),
)


def frozen_units(repetitions: int = 2) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    numeric = 1_000_000
    for repetition in range(1, repetitions + 1):
        for index, truth in enumerate(KNOWN_COMBINATIONS, 1):
            units.append(
                {
                    "id": f"known-c{index:02d}-r{repetition:02d}",
                    "truth": list(truth),
                    "supported": True,
                    "numeric_base": numeric,
                }
            )
            numeric += 20
        for index, truth in enumerate(UNKNOWN_COMBINATIONS, 1):
            units.append(
                {
                    "id": f"unknown-c{index:02d}-r{repetition:02d}",
                    "truth": list(truth),
                    "supported": False,
                    "numeric_base": numeric,
                }
            )
            numeric += 20
    return units


def build_protocol(settle_seconds: float = 1.5, repetitions: int = 2) -> dict[str, Any]:
    panel = greedy_separating_panel()
    return {
        "id": "compound-diagnosis",
        "planner": "minimax-candidate-set",
        "settle_seconds": settle_seconds,
        "repetitions": repetitions,
        "max_steps": 8,
        "known_boundaries": list(BOUNDARIES),
        "unknown_fault": UNKNOWN_FAULT,
        "hypothesis_count": len(hypothesis_space()),
        "fixed_panel": [serialize_set(item) for item in panel],
        "fixed_panel_size": len(panel),
        "units": frozen_units(repetitions),
    }


def case_for(
    unit: dict[str, Any], repairs: Intervention, step: int
) -> dict[str, Any]:
    return case_for_hypothesis(
        unit_id=unit["id"],
        numeric_base=int(unit["numeric_base"]),
        truth=unit["truth"],
        repairs=repairs,
        step=step,
    )

def run_unit(output: Path, unit: dict[str, Any], settle: float, max_steps: int) -> dict[str, Any]:
    candidates = hypothesis_space()
    used: list[Intervention] = []
    repairs: Intervention = frozenset()
    trace: list[dict[str, Any]] = []
    supported_truth = frozenset(value for value in unit["truth"] if value in BOUNDARIES)
    truth_is_supported = bool(unit["supported"])
    outcome = "step_limit"

    for step in range(max_steps):
        before = candidates
        case = case_for(unit, repairs, step)
        record = episode(output.resolve(), case, settle)
        observed = record_signature(record)
        candidates = update_candidates(candidates, repairs, observed)
        contains_truth = supported_truth in candidates if truth_is_supported else None
        trace.append(
            {
                "step": step,
                "execution_id": case["id"],
                "repairs": serialize_set(repairs),
                "repair_breadth": len(repairs),
                "predicted_partition": partition_sizes(before, repairs),
                "observed": observed,
                "status": record.get("status"),
                "candidates_before": len(before),
                "candidates_after": len(candidates),
                "candidate_sets": [serialize_set(item) for item in candidates],
                "truth_retained": contains_truth,
                "stable_latency_ms": record.get("stable_latency_ms"),
                "cpu_s": record.get("metrics", {}).get("cpu_s"),
            }
        )
        used.append(repairs)

        if observed.startswith("noncomparable:"):
            outcome = "infrastructure_or_oracle_error"
            break
        if not candidates:
            outcome = "unmodeled"
            break
        if len(candidates) == 1:
            if truth_is_supported and candidates[0] == supported_truth:
                outcome = "exact"
            elif truth_is_supported:
                outcome = "false_exact"
            else:
                outcome = "unsupported_aliased"
            break
        selected = choose_intervention(candidates, used)
        if selected is None:
            outcome = "unresolved"
            break
        repairs = selected

    return {
        "id": unit["id"],
        "truth": unit["truth"],
        "supported": truth_is_supported,
        "outcome": outcome,
        "exact": outcome == "exact",
        "unmodeled": outcome == "unmodeled",
        "executions": len(trace),
        "repair_breadth_total": sum(item["repair_breadth"] for item in trace),
        "truth_retained_all_modeled_steps": (
            all(item["truth_retained"] is True for item in trace) if truth_is_supported else None
        ),
        "final_candidates": [serialize_set(item) for item in candidates],
        "trace": trace,
    }


def summarize(records: list[dict[str, Any]], protocol: dict[str, Any]) -> dict[str, Any]:
    known = [record for record in records if record["supported"]]
    unknown = [record for record in records if not record["supported"]]
    counts = [record["executions"] for record in known]
    breadth = [record["repair_breadth_total"] for record in known]
    all_traces = [step for record in records for step in record["trace"]]
    summary = {
        "units": len(records),
        "planned_units": len(protocol["units"]),
        "known_units": len(known),
        "unknown_units": len(unknown),
        "actual_process_executions": sum(record["executions"] for record in records),
        "known_exact": sum(record["exact"] for record in known),
        "known_truth_retained": sum(record["truth_retained_all_modeled_steps"] is True for record in known),
        "unknown_unmodeled": sum(record["unmodeled"] for record in unknown),
        "false_exact": sum(record["outcome"] == "false_exact" for record in records),
        "unsupported_aliased": sum(record["outcome"] == "unsupported_aliased" for record in records),
        "noncomparable": sum(record["outcome"] == "infrastructure_or_oracle_error" for record in records),
        "episodes_known_median": statistics.median(counts) if counts else None,
        "episodes_known_min": min(counts) if counts else None,
        "episodes_known_max": max(counts) if counts else None,
        "repair_breadth_known_median": statistics.median(breadth) if breadth else None,
        "fixed_panel_size": protocol["fixed_panel_size"],
        "modeled_observations": sum(step["observed"] in {
            "matched", "upstream_silence", "scheduling_failure", "consumer_failure", "publication_failure"
        } for step in all_traces),
        "completed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return summary


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
        env["diagnosis_model"] = {
            "hypotheses": len(hypothesis_space()),
            "fixed_panel_size": protocol["fixed_panel_size"],
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
            record = run_unit(
                args.output,
                unit,
                float(protocol["settle_seconds"]),
                int(protocol["max_steps"]),
            )
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            print(
                f"{index}/{len(pending)} {unit['id']} {record['outcome']} "
                f"executions={record['executions']}",
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
        if summary["known_exact"] != summary["known_units"]:
            raise SystemExit("Known compound diagnosis did not recover every frozen truth set")
        if summary["known_truth_retained"] != summary["known_units"]:
            raise SystemExit("A modeled observation eliminated its ground-truth hypothesis")
        if summary["unknown_unmodeled"] != summary["unknown_units"]:
            raise SystemExit("An out-of-model mutation did not remain unmodeled")
        if summary["false_exact"] or summary["unsupported_aliased"] or summary["noncomparable"]:
            raise SystemExit("Unsafe or noncomparable compound-diagnosis outcome")


if __name__ == "__main__":
    main()
