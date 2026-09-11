"""Standard-library launcher: one worker, cumulative deadline, strict output cap."""

import argparse
import fcntl
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import time
import uuid

from .config import ROOT, identity, load_config
from .storage import bytes_used, read_json, write_json

THREAD_VARIABLES = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS")


def environment():
    env = os.environ.copy()
    env.update({name: "1" for name in THREAD_VARIABLES})
    env["MPLCONFIGDIR"] = str(ROOT / ".local/matplotlib")
    return env


def versions():
    return {"python": platform.python_version(), **{p: importlib.metadata.version(p)
            for p in ("deap", "numpy", "matplotlib", "pytest")}}


def run_batch(config_path, output):
    cfg = load_config(config_path)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    limit = cfg["output_mib"] * 1024**2
    # One lock shared across output directories; never two experimental workers.
    lock_path = ROOT / ".local/experimental-worker.lock"
    lock_path.parent.mkdir(exist_ok=True)
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("An experimental worker is already active") from exc
        run_id = identity(cfg)
        manifest_path = output / "manifest.json"
        if manifest_path.exists():
            manifest = read_json(manifest_path)
            if manifest["run_id"] != run_id or manifest["versions"] != versions():
                raise ValueError("Incompatible existing experiment; artifacts preserved")
            if manifest["status"] == "complete":
                print("Completed experiment preserved; no worker started.")
                return 0
            if manifest["status"] == "running":
                # Unexpected launcher termination: conservatively charge elapsed time.
                charged = max(0, time.time() - manifest["started_unix"])
                manifest["elapsed_seconds"] += min(charged, manifest["remaining_at_start"])
        else:
            if any(output.iterdir()):
                raise ValueError("Nonempty output without manifest; refusing overwrite")
            order_rng = random.Random(cfg["order_seed"])
            order = []
            for seed in cfg["seeds"]:
                methods = list(cfg["methods"])
                order_rng.shuffle(methods)
                order += [[method, seed] for method in methods]
            revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
            manifest = {"run_id": run_id, "config": cfg, "versions": versions(),
                        "base_git_revision": revision, "order": order,
                        "status": "new", "elapsed_seconds": 0.0, "invocations": [],
                        "experimental_model_calls": 0}
        remaining = cfg["wall_seconds"] - manifest["elapsed_seconds"]
        if remaining <= 2:
            manifest.update(status="partial", failure="Cumulative 1200-second batch budget exhausted")
            write_json(manifest_path, manifest, output, limit)
            print(manifest["failure"])
            return 2
        invocation_id = uuid.uuid4().hex
        manifest.update(status="running", started_unix=time.time(), remaining_at_start=remaining,
                        invocation_id=invocation_id)
        write_json(manifest_path, manifest, output, limit)
        started = time.monotonic()
        command = [sys.executable, "-m", "evolved_circuits.worker", "run", "--output", str(output),
                   "--deadline", str(started + remaining - 1.0), "--lock-fd", str(lock.fileno()),
                   "--invocation-id", invocation_id]
        failure = None
        # The inherited flock stays held if the launcher dies before its worker.
        with subprocess.Popen(command, cwd=ROOT, env=environment(), pass_fds=(lock.fileno(),)) as process:
            try:
                code = process.wait(timeout=max(0.1, remaining - 0.5))
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    code = process.wait(timeout=0.25)
                except subprocess.TimeoutExpired:
                    process.kill()
                    code = process.wait()
                failure = "Hard batch deadline terminated worker; latest durable checkpoint retained"
        elapsed = time.monotonic() - started
        manifest["elapsed_seconds"] += elapsed
        manifest["invocations"].append({"seconds": elapsed, "returncode": code})
        summary_path = output / "worker-summary.json"
        summary = read_json(summary_path) if summary_path.exists() else {}
        if summary.get("invocation_id") != invocation_id:
            summary = {}
        if code and failure is None:
            failure = summary.get("failure") or f"Worker exited with returncode {code} before writing a current summary"
        completed = [f"{method}_{seed}" for method, seed in manifest["order"]
                     if (output / f"{method}_{seed}/result.json").exists()]
        manifest.update(completed=completed, status="complete" if len(completed) == len(manifest["order"]) else "partial",
                        peak_worker_rss_kib=summary.get("peak_rss_kib"),
                        failure=failure or summary.get("failure"), output_bytes=bytes_used(output))
        write_json(manifest_path, manifest, output, limit)
        print(json.dumps({k: manifest[k] for k in ("status", "completed", "elapsed_seconds", "peak_worker_rss_kib", "failure")}))
        return 0 if manifest["status"] == "complete" else (code or 2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run or resume the exact bounded M1 batch")
    run.add_argument("--config", default=str(ROOT / "configs/m1.json"))
    run.add_argument("--output", default=str(ROOT / "artifacts/m1"))
    plot = commands.add_parser("plot", help="Plot saved champion responses and histories")
    plot.add_argument("--output", default=str(ROOT / "artifacts/m1"))
    demo = commands.add_parser("demo", help="Develop an existing program; no search")
    demo.add_argument("--program", required=True)
    demo.add_argument("--f1", type=float, required=True)
    demo.add_argument("--f2", type=float, required=True)
    args = parser.parse_args(argv)
    if args.command == "run":
        return run_batch(args.config, args.output)
    if args.command == "plot":
        os.environ.update({name: "1" for name in THREAD_VARIABLES})
        os.environ["MPLCONFIGDIR"] = str(ROOT / ".local/matplotlib")
        from .plotting import plot_saved
        plot_saved(Path(args.output))
        return 0
    command = [sys.executable, "-m", "evolved_circuits.worker", "demo", "--program", args.program,
               "--f1", str(args.f1), "--f2", str(args.f2)]
    return subprocess.run(command, env=environment(), timeout=30).returncode


if __name__ == "__main__":
    raise SystemExit(main())
