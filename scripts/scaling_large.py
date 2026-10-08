#!/usr/bin/env python3
"""Run and compact the frozen 1k/5k-file scaling holdout.

The small-tree study retained complete trees for 10 and 250 files. At 5,000 files that
layout would dominate the artifact with duplicated generated files, so this
runner retains the complete JSON projections, event/timeline logs, source
fingerprint, and representative source/output bytes, then removes duplicate
working and clean trees.  Every episode remains rerunnable from its frozen job.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import statistics
import subprocess
import tempfile
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
from watchdelta.core import source_files, source_fingerprint
from watchdelta.run import environment, episode

SIZES = [1_000, 5_000]
REPETITIONS = 2


def mount(path: Path) -> dict[str, Any]:
    text = subprocess.check_output(
        ["findmnt", "-T", str(path), "-J", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS"],
        text=True,
    )
    return json.loads(text)["filesystems"][0]


def jobs() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    numeric = 1_100_000
    for filesystem in ["overlay", "tmpfs"]:
        for tool, modes in [("tsc", ["default", "hash"]), ("docs", ["relevant", "hash"])]:
            for mode in modes:
                for size in SIZES:
                    for repetition in range(1, REPETITIONS + 1):
                        result.append(
                            {
                                "id": f"{filesystem}-{tool}-{mode}-n{size}-r{repetition:02d}",
                                "numeric_id": numeric,
                                "filesystem": filesystem,
                                "tool": tool,
                                "mode": mode,
                                "scenario": "same_size",
                                "inject": "none",
                                "diagnostic": False,
                                "file_count": size,
                            }
                        )
                        numeric += 1
    return result


def build_protocol(settle_seconds: float = 2.5) -> dict[str, Any]:
    return {
        "id": "scaling-large",
        "settle_seconds": settle_seconds,
        "sizes": SIZES,
        "repetitions_per_filesystem": REPETITIONS,
        "retention": "complete projections and logs plus representative bytes; duplicate trees compacted",
        "jobs": jobs(),
    }


def copy_if_present(source: Path, destination: Path) -> None:
    if source.exists() and source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def compact_episode(folder: Path, record: dict[str, Any]) -> dict[str, Any]:
    work = folder / "work"
    clean = folder / "clean"
    tool = record["tool"]
    source_suffix = ".ts" if tool == "tsc" else ".md"
    output_suffix = ".js" if tool == "tsc" else ".html"
    fingerprint, source_bytes = source_fingerprint(work, tool)
    source_count = len(source_files(work, tool))
    observed_count = len(record["observed_projection"])
    clean_count = len(record["clean"]["projection"])

    sample = folder / "retained-samples"
    if tool == "docs":
        copy_if_present(work / "src/index.md", sample / "work/src/index.md")
        copy_if_present(folder / "observed/index.html", sample / "observed/index.html")
        copy_if_present(clean / "out/index.html", sample / "clean/out/index.html")
    else:
        copy_if_present(work / "src/message.ts", sample / "work/src/message.ts")
        copy_if_present(folder / "observed/message.js", sample / "observed/message.js")
        copy_if_present(folder / "observed/index.js", sample / "observed/index.js")
        copy_if_present(clean / "out/message.js", sample / "clean/out/message.js")
        copy_if_present(clean / "out/index.js", sample / "clean/out/index.js")

    manifest = {
        "source_suffix": source_suffix,
        "output_suffix": output_suffix,
        "source_files": source_count,
        "source_bytes": source_bytes,
        "source_sha256": fingerprint,
        "recorded_source_sha256": record["clean"]["source_sha256"],
        "observed_outputs": observed_count,
        "clean_outputs": clean_count,
        "observed_projection_sha256": hashlib.sha256(
            json.dumps(record["observed_projection"], sort_keys=True).encode()
        ).hexdigest(),
        "clean_projection_sha256": hashlib.sha256(
            json.dumps(record["clean"]["projection"], sort_keys=True).encode()
        ).hexdigest(),
        "compacted_paths": ["work", "observed", "clean", "manual_rebuild"],
    }
    if source_count != record["file_count"]:
        raise RuntimeError(f"Source count mismatch before compaction: {record['id']}")
    if fingerprint != record["clean"]["source_sha256"]:
        raise RuntimeError(f"Source fingerprint mismatch before compaction: {record['id']}")
    if record["observed_projection"] != record["clean"]["projection"]:
        raise RuntimeError(f"Cannot compact mismatching scaling endpoint: {record['id']}")
    (folder / "retained-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for name in manifest["compacted_paths"]:
        path = folder / name
        if path.exists():
            shutil.rmtree(path)
    return manifest


def summarize(records: list[dict[str, Any]], plan: list[dict[str, Any]]) -> dict[str, Any]:
    cells: list[dict[str, Any]] = []
    for filesystem in ["overlay", "tmpfs"]:
        for tool, modes in [("tsc", ["default", "hash"]), ("docs", ["relevant", "hash"])]:
            for mode in modes:
                for size in SIZES:
                    selected = [
                        record
                        for record in records
                        if record["filesystem"] == filesystem
                        and record["tool"] == tool
                        and record["mode"] == mode
                        and record["file_count"] == size
                    ]
                    cells.append(
                        {
                            "filesystem": filesystem,
                            "tool": tool,
                            "mode": mode,
                            "file_count": size,
                            "n": len(selected),
                            "matched": sum(record["status"] == "matched" for record in selected),
                            "setup_to_ready_median_ms": statistics.median(
                                record["setup_to_ready_ms"] for record in selected
                            )
                            if selected
                            else None,
                            "stable_latency_median_ms": statistics.median(
                                record["stable_latency_ms"]
                                for record in selected
                                if record.get("stable_latency_ms") is not None
                            )
                            if selected
                            else None,
                            "cpu_median_ms": statistics.median(
                                record["metrics"]["cpu_s"] * 1000 for record in selected
                            )
                            if selected
                            else None,
                            "scan_median_mib": statistics.median(
                                record["metrics"]["scan_bytes"] / (1024 * 1024) for record in selected
                            )
                            if selected
                            else None,
                        }
                    )
    return {
        "episodes": len(records),
        "planned_episodes": len(plan),
        "matched": sum(record["status"] == "matched" for record in records),
        "stale": sum(record["status"] == "stale" for record in records),
        "infrastructure_error": sum(record["status"] == "infrastructure_error" for record in records),
        "cells": cells,
        "completed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-jobs", type=int)
    args = parser.parse_args()

    if args.protocol:
        raw = args.protocol.read_bytes()
        protocol = json.loads(raw)
    else:
        protocol = build_protocol()
        raw = (json.dumps(protocol, indent=2, sort_keys=True) + "\n").encode()
    plan = protocol["jobs"]

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
        env["mounts"] = {"overlay": mount(args.output), "tmpfs": mount(Path("/dev/shm"))}
        (args.output / "environment.json").write_text(json.dumps(env, indent=2) + "\n")
        (args.output / "records.jsonl").write_text("")

    records = [
        json.loads(line)
        for line in (args.output / "records.jsonl").read_text().splitlines()
        if line.strip()
    ]
    completed = {record["id"] for record in records}
    pending = [job for job in plan if job["id"] not in completed]
    if args.max_jobs is not None:
        pending = pending[: args.max_jobs]

    tmpbase = Path(tempfile.mkdtemp(prefix="watchdelta-scaling-large-", dir="/dev/shm"))
    try:
        with (args.output / "records.jsonl").open("a") as handle:
            for index, job in enumerate(pending, 1):
                base = args.output if job["filesystem"] == "overlay" else tmpbase
                target = args.output / "episodes" / job["id"]
                if target.exists():
                    shutil.rmtree(target)
                source = tmpbase / "episodes" / job["id"]
                if source.exists():
                    shutil.rmtree(source)
                call_start_ns = time.monotonic_ns()
                record = episode(base.resolve(), job, float(protocol["settle_seconds"]))
                record["setup_to_ready_ms"] = (record["ready_ns"] - call_start_ns) / 1e6
                if job["filesystem"] == "tmpfs":
                    shutil.copytree(source, target)
                    shutil.rmtree(source)
                compact_episode(target, record)
                (target / "record.json").write_text(json.dumps(record, indent=2) + "\n")
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                handle.flush()
                print(
                    f"{index}/{len(pending)} {job['id']} {record['status']} "
                    f"ready={record['setup_to_ready_ms']:.1f}ms",
                    flush=True,
                )
    finally:
        shutil.rmtree(tmpbase, ignore_errors=True)

    records = [
        json.loads(line)
        for line in (args.output / "records.jsonl").read_text().splitlines()
        if line.strip()
    ]
    summary = summarize(records, plan)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    if len(records) == len(plan):
        (args.output / "complete.json").write_text(
            json.dumps(
                {"episodes": len(records), "completed_utc": summary["completed_utc"]},
                indent=2,
            )
            + "\n"
        )
    print(json.dumps({key: summary[key] for key in summary if key != "cells"}, indent=2))
    if len(records) == len(plan) and summary["matched"] != len(plan):
        raise SystemExit("Large-tree scaling endpoint mismatch")


if __name__ == "__main__":
    main()
