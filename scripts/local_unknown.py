"""Truth-blinded local selector/scope repair comparison (standard library only).

This is a separate one-file polling fixture, not watchfiles or the 32-hypothesis
mutation harness. The driver seeds a bad suffix or root; repair() receives only
an opaque running process and final reference bytes. It changes actual observer
configuration, never removes a fault by looking up its seeded label.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import queue
import random
import statistics
import subprocess
import sys
import threading
import time


def worker(root: Path, scope: str, suffix: str) -> None:
    commands: queue.Queue = queue.Queue()
    def read_commands():
        for line in sys.stdin:
            commands.put(json.loads(line))
    threading.Thread(target=read_commands, daemon=True).start()
    builds = scans = 0
    def build():
        nonlocal builds
        # The deterministic consumer reads source bytes, not an expected token.
        (root / "output.txt").write_bytes((root / "src/input.md").read_bytes().upper())
        builds += 1
    def scan():
        nonlocal scans
        scans += 1
        return {p.relative_to(root).as_posix(): (p.stat().st_mtime_ns, p.stat().st_size)
                for p in sorted((root / scope).glob("*" + suffix)) if p.is_file()}
    build()
    previous = scan()
    print(json.dumps({"ready": True}), flush=True)
    while True:
        try: command = commands.get(timeout=.01)
        except queue.Empty: command = None
        if command:
            if command["action"] == "stop": return
            if command["action"] == "selection": suffix = ".md"
            if command["action"] == "scope": scope = "src"
            if command["action"] == "manual": build()
        current = scan()
        if current != previous:
            previous = current
            build()
        if command:
            print(json.dumps({"cpu_ns": time.process_time_ns(), "builds": builds,
                              "scans": scans, "output": (root / "output.txt").read_bytes().decode("utf-8")}), flush=True)


class Session:
    """Command transport contains neither a truth label nor a repair lookup."""
    def __init__(self, root: Path, scope: str, suffix: str):
        self.process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--worker", str(root),
             "--scope", scope, "--suffix", suffix],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", cwd=root)
        self.responses: queue.Queue = queue.Queue()
        def reader():
            for line in self.process.stdout:
                self.responses.put(json.loads(line))
        threading.Thread(target=reader, daemon=True).start()
        if self.responses.get(timeout=5) != {"ready": True}:
            raise RuntimeError("readiness failed")
    def command(self, action="snapshot"):
        self.process.stdin.write(json.dumps({"action": action}) + "\n")
        self.process.stdin.flush()
        return self.responses.get(timeout=5)
    def stop(self):
        if self.process.poll() is None:
            self.process.stdin.write('{"action":"stop"}\n')
            self.process.stdin.flush()
            self.process.wait(timeout=5)
        stderr = self.process.stderr.read()
        if self.process.returncode != 0 or stderr:
            raise RuntimeError(f"local worker failed: {stderr}")


def endpoint(session: Session, expected: str, budget=.2):
    """Fixed-budget sampling; a transient agreement is not a final agreement."""
    start = time.perf_counter_ns()
    samples = []
    deadline = time.monotonic() + budget
    while time.monotonic() < deadline:
        samples.append({"t_ns": time.perf_counter_ns(), **session.command()})
        time.sleep(.01)
    samples.append({"t_ns": time.perf_counter_ns(), **session.command()})
    matched = samples[-1]["output"] == expected
    index = len(samples) - 1
    if matched:
        while index > 0 and samples[index - 1]["output"] == expected: index -= 1
    return {"matched": matched, "samples": samples,
            "latency_ms": (samples[index]["t_ns"] - start) / 1e6 if matched else None}


def repair(session: Session, expected: str, strategy: str):
    """Apply literal configuration edits to the existing process, without truth."""
    if strategy == "unchanged": return []
    if strategy == "manual": session.command("manual"); return ["manual"]
    session.command("selection")
    if endpoint(session, expected)["matched"]: return ["selection"]
    session.command("scope")
    return ["selection", "scope"]


def run(output: Path, repetitions: int):
    output.mkdir(parents=True, exist_ok=False)
    faults = [fault for _ in range(repetitions) for fault in ("selection", "scope")]
    random.Random(121).shuffle(faults)
    records = []
    for unit, fault in enumerate(faults):
        for strategy in ("unchanged", "manual", "configured"):
            root = output / f"u{unit:02d}-{strategy}"
            (root / "src").mkdir(parents=True)
            (root / "unrelated").mkdir()
            source = root / "src/input.md"
            source.write_text("initial\n", encoding="utf-8")
            scope, suffix = ("src", ".txt") if fault == "selection" else ("unrelated", ".md")
            session = Session(root, scope, suffix)
            try:
                initial = session.command()
                if initial["output"] != source.read_bytes().upper().decode("utf-8"): raise RuntimeError("initial consumer mismatch")
                source.write_text("first terminal edit\n", encoding="utf-8")
                # Independent byte reference; never supplied to the worker.
                reference = source.read_bytes().upper().decode("utf-8")
                (root / "reference-first.txt").write_bytes(reference.encode("utf-8"))
                base = endpoint(session, reference)
                if base["matched"]: raise RuntimeError("seeded baseline unexpectedly passed")
                before = session.command()
                start = time.perf_counter_ns()
                actions = repair(session, reference, strategy)
                after = session.command()
                intervention_ms = (time.perf_counter_ns() - start) / 1e6
                repaired = endpoint(session, reference)
                source.write_text("second terminal edit\n", encoding="utf-8")
                reference2 = source.read_bytes().upper().decode("utf-8")
                (root / "reference-second.txt").write_bytes(reference2.encode("utf-8"))
                followup = endpoint(session, reference2)
                records.append({"unit": unit, "seeded_configuration": fault, "strategy": strategy,
                                "actions": actions, "baseline": base, "repaired": repaired,
                                "followup": followup, "intervention_wall_ms": intervention_ms,
                                "intervention_cpu_ms": (after["cpu_ns"] - before["cpu_ns"]) / 1e6,
                                "intervention_scans": after["scans"] - before["scans"],
                                "intervention_builds": after["builds"] - before["builds"]})
            finally: session.stop()
    summary = {"python": sys.version, "platform": sys.platform,
               "fixture": "one-file standard-library metadata observer and uppercase-byte consumer",
               "units": len(faults), "processes": len(records), "budget_seconds": .2,
               "strategies": {}}
    for strategy in ("unchanged", "manual", "configured"):
        selected = [record for record in records if record["strategy"] == strategy]
        summary["strategies"][strategy] = {
            "n": len(selected), "baseline_matched": sum(r["baseline"]["matched"] for r in selected),
            "repaired_matched": sum(r["repaired"]["matched"] for r in selected),
            "followup_matched": sum(r["followup"]["matched"] for r in selected),
            "intervention_wall_median_ms": statistics.median(r["intervention_wall_ms"] for r in selected),
            "intervention_cpu_median_ms": statistics.median(r["intervention_cpu_ms"] for r in selected),
            "intervention_scans_median": statistics.median(r["intervention_scans"] for r in selected),
            "intervention_builds_total": sum(r["intervention_builds"] for r in selected)}
    (output / "records.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--scope")
    parser.add_argument("--suffix")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repetitions", type=int, default=4)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.scope, args.suffix)
    else:
        if args.output is None or args.repetitions < 1: parser.error("output and positive repetitions required")
        run(args.output.resolve(), args.repetitions)


if __name__ == "__main__": main()
