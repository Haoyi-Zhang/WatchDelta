"""Sequential end-to-end tests of Hypercorn 0.18.0's real reload supervisor.

Each episode starts a fresh ``python -m hypercorn app:app --reload`` process,
waits for an HTTP response from the initial source, applies one bounded edit,
then compares the served response with fresh-process evaluation of identical
final source.  This does not mock Hypercorn's polling reloader.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

TOKEN0 = "WD0000000000"

APP_TEMPLATE = '''from __future__ import annotations
CONTENT = "{token}"
print("WATCHDELTA_HYPERCORN_IMPORT", CONTENT, flush=True)

async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            event = await receive()
            if event["type"] == "lifespan.startup":
                await send({{"type": "lifespan.startup.complete"}})
            elif event["type"] == "lifespan.shutdown":
                await send({{"type": "lifespan.shutdown.complete"}})
                return
    elif scope["type"] == "http":
        body = CONTENT.encode("utf-8")
        await send({{"type": "http.response.start", "status": 200,
                     "headers": [(b"content-type", b"text/plain; charset=utf-8")]}})
        await send({{"type": "http.response.body", "body": body}})
'''


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_app(token: str, append: str = "") -> str:
    return APP_TEMPLATE.format(token=token) + append


def fresh_import(project: Path) -> dict[str, Any]:
    # Read and execute the final source bytes directly in a fresh interpreter.
    # Importing from the measured directory is not independent: a same-size,
    # restored-mtime edit can make CPython accept a pre-edit .pyc file.
    code = (
        "import json,pathlib,sys; p=pathlib.Path(sys.argv[1]); "
        "source=p.read_bytes(); ns={}; "
        "exec(compile(source, str(p), 'exec'), ns); "
        "print('WATCHDELTA_ORACLE='+json.dumps(ns['CONTENT']))"
    )
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", code, str(project / "app.py")],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
    )
    marker = "WATCHDELTA_ORACLE="
    payload = None
    for line in result.stdout.splitlines():
        if line.startswith(marker):
            payload = json.loads(line[len(marker):])
    return {
        "returncode": result.returncode,
        "content": payload,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": [sys.executable, "-c", "<fresh-import>", "<project>"],
    }


def read_http(port: int, timeout: float = 0.5) -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=timeout) as response:
        return response.read().decode("utf-8")


def apply_edit(project: Path, scenario: str, token: str) -> dict[str, Any]:
    target = project / "app.py"
    old = target.read_bytes()
    new = old.replace(TOKEN0.encode(), token.encode())
    if len(token) != len(TOKEN0):
        raise ValueError("replacement token must preserve byte length")
    before = target.stat()
    start = time.monotonic_ns()
    writes = 0
    if scenario in {"same_size", "preserved_stat"}:
        target.write_bytes(new)
        writes = 1
        if scenario == "preserved_stat":
            os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
    elif scenario == "inplace":
        target.write_bytes(new + b"\n# measured in-place extension\n")
        writes = 1
    elif scenario == "atomic":
        temp = target.with_name(".app.py.wd-stage")
        temp.write_bytes(new)
        os.replace(temp, target)
        writes = 1
    elif scenario == "burst":
        for index in range(8):
            interim = old.replace(TOKEN0.encode(), f"WB{index:010d}".encode())
            target.write_bytes(interim)
            writes += 1
            time.sleep(0.035)
        target.write_bytes(new)
        writes += 1
    elif scenario == "temporary":
        temp = project / ".app.py.wd-editor"
        for index in range(3):
            temp.write_text(f"editor buffer {index}\n", encoding="utf-8")
            writes += 1
            time.sleep(0.03)
        temp.unlink()
        writes += 1
    else:
        raise ValueError(scenario)
    end = time.monotonic_ns()
    after = target.stat()
    return {
        "start_ns": start,
        "end_ns": end,
        "writes": writes,
        "obligation": scenario != "temporary",
        "same_size": len(old) == len(target.read_bytes()),
        "mtime_before_ns": before.st_mtime_ns,
        "mtime_after_ns": after.st_mtime_ns,
        "mtime_restored": after.st_mtime_ns == before.st_mtime_ns,
        "source_sha256": sha256(target),
    }


def wait_ready(process: subprocess.Popen[str], port: int, expected: str, timeout: float) -> tuple[int, str]:
    limit = time.monotonic() + timeout
    last = ""
    while time.monotonic() < limit:
        if process.poll() is not None:
            raise RuntimeError(f"Hypercorn exited before readiness: {process.returncode}")
        try:
            last = read_http(port, timeout=0.3)
            if last == expected:
                return time.monotonic_ns(), last
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.035)
    raise TimeoutError(f"Hypercorn readiness; last={last!r}")


def terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        # Hypercorn handles SIGINT as an orderly shutdown request. The hard kill
        # is only a bounded post-measurement cleanup fallback.
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def environment() -> dict[str, Any]:
    import hypercorn.run
    import hypercorn.utils

    run_path = Path(hypercorn.run.__file__).resolve()
    utils_path = Path(hypercorn.utils.__file__).resolve()
    return {
        "python": sys.version,
        "hypercorn": importlib.metadata.version("hypercorn"),
        "platform": sys.platform,
        "reload_source": {
            "run.py": {"path": str(run_path), "sha256": sha256(run_path)},
            "utils.py": {"path": str(utils_path), "sha256": sha256(utils_path)},
        },
        "mechanism": "supervisor calls files_to_watch(), then check_for_updates() at one-second wait intervals",
    }


def run_episode(output: Path, job: dict[str, Any], settle_seconds: float) -> dict[str, Any]:
    folder = output / "episodes" / job["id"]
    folder.mkdir(parents=True)
    project = (folder / "work").resolve()
    project.mkdir()
    (project / "app.py").write_text(render_app(TOKEN0), encoding="utf-8")
    record: dict[str, Any] = {**job, "status": "infrastructure_error"}
    process: subprocess.Popen[str] | None = None
    log_path = folder / "server.log"
    token = f"WD{job['numeric_id']:010d}"
    wall_start_ns = time.monotonic_ns()
    with log_path.open("w", encoding="utf-8") as log:
        try:
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            sock.close()
            command = [
                sys.executable,
                "-m",
                "hypercorn",
                "app:app",
                "--bind",
                f"127.0.0.1:{port}",
                "--reload",
                "--workers",
                "1",
                "--worker-class",
                "asyncio",
                "--log-level",
                "warning",
            ]
            process = subprocess.Popen(
                command,
                cwd=project,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            ready_ns, initial = wait_ready(process, port, TOKEN0, timeout=25)
            log.flush()
            initial_imports = log_path.read_text(encoding="utf-8", errors="replace").count(
                "WATCHDELTA_HYPERCORN_IMPORT"
            )
            edit_info = apply_edit(project, job["scenario"], token)
            deadline = edit_info["end_ns"] / 1e9 + settle_seconds
            samples: list[dict[str, Any]] = []
            while time.monotonic() < deadline:
                now = time.monotonic_ns()
                try:
                    samples.append({"t_ns": now, "content": read_http(port, timeout=0.35)})
                except Exception as exc:  # transient worker restart is an observed state
                    samples.append({"t_ns": now, "error": type(exc).__name__})
                time.sleep(0.08)
            observed = read_http(port, timeout=3)
            endpoint_ns = time.monotonic_ns()
            # Freeze the source before constructing the independent reference.
            reference_dir = folder / 'reference'
            reference_dir.mkdir()
            shutil.copy2(project / 'app.py', reference_dir / 'app.py')
            source_before = sha256(project / 'app.py')
            oracle = fresh_import(reference_dir)
            source_stable = (source_before == sha256(project / 'app.py')
                             == sha256(reference_dir / 'app.py'))
            expected = oracle["content"]
            status = (
                "oracle_error"
                if oracle["returncode"] != 0 or expected is None or not source_stable
                else ("matched" if observed == expected else "stale")
            )
            log.flush()
            total_imports = log_path.read_text(encoding="utf-8", errors="replace").count(
                "WATCHDELTA_HYPERCORN_IMPORT"
            )
            target = project / "app.py"
            shutil.copy2(target, folder / "final-app.py")
            samples.append({'t_ns': endpoint_ns, 'content': observed})
            (folder / "samples.jsonl").write_text(
                "".join(json.dumps(sample) + "\n" for sample in samples), encoding="utf-8"
            )
            last_nonmatch = max((i for i, sample in enumerate(samples)
                                 if sample.get('content') != expected), default=-1)
            first_expected = (samples[last_nonmatch + 1]['t_ns']
                              if last_nonmatch + 1 < len(samples) else None)
            record.update(
                status=status,
                initial=initial,
                expected=expected,
                observed=observed,
                oracle=oracle,
                source_stable=source_stable,
                latency_definition='first sample of final matching suffix',
                ready_ns=ready_ns,
                endpoint_ns=endpoint_ns,
                edit=edit_info,
                reload_imports=max(0, total_imports - initial_imports),
                observation_ms=(endpoint_ns - edit_info["end_ns"]) / 1e6,
                response_latency_ms=(
                    (first_expected - edit_info["end_ns"]) / 1e6
                    if first_expected is not None and edit_info["obligation"]
                    else None
                ),
                transient_errors=sum("error" in sample for sample in samples),
                command=[item.replace(str(project), "<project>") for item in command],
                source_sha256=sha256(target),
                startup_ms=(ready_ns - wall_start_ns) / 1e6,
            )
        except Exception as exc:
            record.update(error=repr(exc))
        finally:
            if process is not None:
                terminate(process)
            record["episode_wall_ms"] = (time.monotonic_ns() - wall_start_ns) / 1e6
    (folder / "record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite result directory")
    protocol_bytes = args.protocol.read_bytes()
    protocol = json.loads(protocol_bytes)
    args.output.mkdir(parents=True)
    (args.output / "protocol.json").write_bytes(protocol_bytes)
    (args.output / "protocol.sha256").write_text(
        hashlib.sha256(protocol_bytes).hexdigest() + "\n", encoding="utf-8"
    )
    (args.output / "environment.json").write_text(
        json.dumps(environment(), indent=2) + "\n", encoding="utf-8"
    )
    records = []
    with (args.output / "records.jsonl").open("w", encoding="utf-8") as stream:
        for index, job in enumerate(protocol["jobs"]):
            record = run_episode(args.output, job, protocol["settle_seconds"])
            records.append(record)
            stream.write(json.dumps(record) + "\n")
            stream.flush()
            print(
                f"{index + 1}/{len(protocol['jobs'])} {job['id']} "
                f"{record['status']} reloads={record.get('reload_imports')}",
                flush=True,
            )
    counts: dict[str, int] = {}
    for record in records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    (args.output / "complete.json").write_text(
        json.dumps({"episodes": len(records), "status": counts}, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
