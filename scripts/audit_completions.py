#!/usr/bin/env python3
"""Audit legacy completion flags without modifying archived observations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    parser.add_argument("--output", type=Path, default=ROOT / "evidence" / "completion-field-audit.json")
    args = parser.parse_args()
    rows = []
    for name in ["primary-matrix", "sensitivity", "timing-diagnostic", "baseline-challenge", "long-budget"]:
        records_path = args.results / name / "records.jsonl"
        for line in records_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            event_path = args.results / name / "episodes" / record["id"] / "events.jsonl"
            events = [json.loads(item) for item in event_path.read_text(encoding="utf-8").splitlines() if item.strip()]
            stats = [event for event in events if event["kind"] == "stats"]
            if len(stats) != 2:
                raise RuntimeError((record["id"], "expected exactly two metric snapshots"))
            count = sum(
                event.get("kind") == "build_end"
                and event.get("returncode") == 0
                and stats[0]["t_ns"] < event.get("t_ns", -1) <= stats[-1]["t_ns"]
                for event in events
            )
            rows.append(
                {
                    "dataset": name,
                    "id": record["id"],
                    "successful_end_events": count,
                    "legacy_flag": record.get("completion_observed"),
                    "agrees": record["completion_observed"] == (count > 0)
                    if "completion_observed" in record
                    else None,
                }
            )
    report = {
        "episodes_checked": len(rows),
        "legacy_flags_present": sum(row["agrees"] is not None for row in rows),
        "flag_disagreements": sum(row["agrees"] is False for row in rows),
        "other_schema_without_legacy_flag": sum(row["agrees"] is None for row in rows),
        "raw_records_modified": False,
        "scope": (
            "Uvicorn and Hypercorn use separate reload-record schemas; pilots and mechanism replays are not part "
            "of this main/diagnostic completion-field audit. Agreement does not make the legacy formula generally valid."
        ),
        "episodes": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "episodes"}, indent=2))
    return 1 if report["flag_disagreements"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
