"""Mandatory endpoint premises, separate from diagnostic model conformance.

``stale`` is a nonconforming byte endpoint; ``nonconform`` is a consumer
disagreement even if disk bytes match. ``inconclusive`` means the reference,
readiness, or capture premise is not established. Missing evidence is not True.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

from .core import projection, source_fingerprint


@dataclass(frozen=True)
class Qualification:
    status: str
    reasons: tuple[str, ...] = ()

    @property
    def verdict(self) -> str:
        return {"matched": "conform", "stale": "nonconform",
                "nonconform": "nonconform", "inconclusive": "inconclusive"}[self.status]


def qualify(record: dict[str, Any], *, ready_ns: int | None = None) -> Qualification:
    """Recompute a verdict without trusting the serialized status.

    Older timing records retain readiness in events rather than record.json;
    the retained-record validator supplies that timestamp explicitly. Older
    single-page CLI records retain the HTTP comparison flag but not HTTP bytes.
    That flag is required, not silently treated as a successful missing probe.
    """
    missing: list[str] = []
    clean = record.get("clean", {})
    expected = clean.get("projection")
    observed = record.get("observed_projection")
    if type(clean.get("returncode")) is not int or clean["returncode"] != 0:
        missing.append("reference did not exit successfully")
    if not isinstance(expected, dict) or not expected:
        missing.append("reference projection missing or empty")
    if not isinstance(observed, dict):
        missing.append("observed projection missing")
    if not clean.get("source_sha256"):
        missing.append("terminal source fingerprint missing")
    edit = record.get("edit", {})
    ready = record.get("ready_ns", ready_ns)
    start, end = edit.get("start_ns"), edit.get("end_ns")
    if not all(type(value) is int for value in (ready, start, end)) or not ready <= start <= end:
        missing.append("readiness/edit clock order not established")
    if record.get("snapshot_stable") is not True:
        missing.append("stable endpoint snapshot not established")
    obligation = edit.get("obligation")
    if type(obligation) is not bool:
        missing.append("edit obligation missing")
    scenario = record.get("scenario")
    # The frozen timing protocol stores condition, not scenario; its reviewed
    # driver always performs an ordinary same_size edit (not restored metadata).
    if scenario is None and record.get("stratum") == "post_discovery_timing" and record.get("condition") in {"same_second", "cross_second"}:
        scenario = "same_size"
    if "initial_projection" in record:
        initial = record["initial_projection"]
        if not isinstance(initial, dict) or not initial:
            missing.append("nonempty initial output not established")
        elif isinstance(expected, dict) and ((initial != expected) != obligation):
            missing.append("edit obligation differs from initial/reference comparison")
        if record.get("obligation_consistent") is not True:
            missing.append("edit obligation check not established")
    elif scenario not in {"inplace", "same_size", "atomic", "burst",
                                         "newdir", "temporary", "chunked", "preserved_stat"}:
        missing.append("legacy edit obligation cannot be checked")
    elif obligation != (scenario != "temporary"):
        missing.append("edit obligation differs from declared edit program")

    consumer_mismatch: list[str] = []
    if record.get("tool") == "docs":
        flag = record.get("served_matches_disk")
        served = record.get("served_projection")
        if isinstance(served, dict):
            agrees = served == observed
            if type(flag) is not bool or flag != agrees:
                missing.append("HTTP comparison flag missing or inconsistent")
            if not agrees:
                consumer_mismatch.append("served output differs from captured disk output")
        elif flag is False:
            consumer_mismatch.append("served output differs from captured disk output")
        elif flag is not True:
            missing.append("HTTP/disk agreement not established")
    elif record.get("tool") == "tsc":
        live, reference = record.get("runtime"), record.get("clean_runtime")
        if not isinstance(reference, dict) or reference.get("returncode") != 0:
            missing.append("reference consumer execution not successful")
        if not isinstance(live, dict):
            missing.append("live consumer execution missing")
        elif isinstance(reference, dict):
            if record.get("runtime_matches") is not (live == reference):
                missing.append("runtime comparison flag missing or inconsistent")
            if live.get("returncode") != 0 or live != reference:
                consumer_mismatch.append("live consumer differs from successful reference")
    else:
        missing.append("unsupported endpoint tool")
    if missing:
        return Qualification("inconclusive", tuple(missing))
    if observed != expected:
        return Qualification("stale", tuple(consumer_mismatch))
    if consumer_mismatch:
        return Qualification("nonconform", tuple(consumer_mismatch))
    return Qualification("matched")


def validate_retained(record: dict[str, Any], folder: Path) -> Qualification:
    """Check premises and their retained byte/source witnesses on every path."""
    ready = None
    events_path = folder / "events.jsonl"
    if "ready_ns" not in record and events_path.is_file():
        events = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
        ready = next((event.get("t_ns") for event in events if event.get("kind") == "ready"), None)
    result = qualify(record, ready_ns=ready)
    if result.status == "inconclusive":
        raise RuntimeError(f"inconclusive episode {record.get('id')}: {'; '.join(result.reasons)}")
    if record.get("status") != result.status:
        raise RuntimeError(f"endpoint misclassification {record.get('id')}: stored={record.get('status')} recomputed={result.status}")
    ext = ".js" if record["tool"] == "tsc" else ".html"
    if projection(folder / "observed", ext) != record["observed_projection"]:
        raise RuntimeError(f"retained observed bytes differ: {record.get('id')}")
    if projection(folder / "clean/out", ext) != record["clean"]["projection"]:
        raise RuntimeError(f"retained reference bytes differ: {record.get('id')}")
    for tree in ("work", "clean"):
        if source_fingerprint(folder / tree, record["tool"])[0] != record["clean"]["source_sha256"]:
            raise RuntimeError(f"retained terminal source differs ({tree}): {record.get('id')}")
    if record["tool"] == "tsc" and (folder / "work/tsconfig.json").read_bytes() != (folder / "clean/tsconfig.json").read_bytes():
        raise RuntimeError(f"compiler options differ: {record.get('id')}")
    return result
