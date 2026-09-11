"""Set address-space/thread limits BEFORE importing NumPy, DEAP, or package core."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import random
import resource
import sys
import time


def apply_limits(memory_mib=768):
    if not 0 < memory_mib <= 768:
        raise ValueError("Worker cap must be at most 768 MiB")
    if "numpy" in sys.modules:
        raise RuntimeError("Numerical library imported before address-space limit")
    resource.setrlimit(resource.RLIMIT_AS, (memory_mib * 1024**2, memory_mib * 1024**2))
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS"):
        os.environ[key] = "1"


def execute(output, deadline, invocation_id):
    from .assessment import assess
    from .config import identity
    from .evaluation import TrainingEvaluator
    from .language import initial, make_pset
    from .search import DeadlineReached, run_search
    from .storage import read_json, write_json, write_text
    manifest = read_json(output / "manifest.json")
    cfg, run_id = manifest["config"], manifest["run_id"]
    if identity(cfg) != run_id:
        raise ValueError("Source/configuration changed since launcher validation")
    limit = cfg["output_mib"] * 1024**2
    summary = {"status": "partial", "failure": None, "peak_rss_kib": None,
               "invocation_id": invocation_id,
               "address_limit_bytes": resource.getrlimit(resource.RLIMIT_AS)[0],
               "numpy_import_after_limit": True,
               "experimental_model_calls": 0, "worker_pid": os.getpid()}
    try:
        timing_path = output / "timing.json"
        if not timing_path.exists():
            random.seed(cfg["timing_seed"])
            pset = make_pset(cfg)
            evaluator = TrainingEvaluator(cfg)
            start = time.monotonic()
            for _ in range(cfg["timing_candidates"]):
                if time.monotonic() >= deadline:
                    raise DeadlineReached("Deadline in timing sample")
                evaluator.evaluate(initial(pset, cfg))
            # Deliberately discard losses; timing is not search evidence.
            write_json(timing_path, {"candidates": cfg["timing_candidates"], "seed": cfg["timing_seed"],
                                     "seconds": time.monotonic() - start, "used_for_selection": False}, output, limit)
        for method, seed in manifest["order"]:
            directory = output / f"{method}_{seed}"
            result_path = directory / "result.json"
            if result_path.exists():
                if read_json(result_path)["run_id"] != run_id:
                    raise ValueError("Incompatible completed run")
                continue
            checkpoint = directory / "checkpoint.json"
            state = read_json(checkpoint) if checkpoint.exists() else None
            def save(value):
                write_json(checkpoint, value, output, limit)
            state = run_search(cfg, method, seed, run_id, save, deadline, state)
            if time.monotonic() >= deadline:
                raise DeadlineReached("Search saved; assessment still pending")
            start = time.monotonic()
            assessment = assess(state, cfg)
            assessment_seconds = time.monotonic() - start
            # Never replace existing completed evidence. A result is the completion marker.
            write_json(directory / "assessment.json", assessment, output, limit)
            write_text(directory / "program.txt", state["champion"]["program"] + "\n", output, limit)
            write_json(directory / "history.json", state["history"], output, limit)
            for case in assessment["dense_training"]["cases"]:
                if min(case["f1"], case["f2"]) == 10000 and not case["invalid"]:
                    write_text(directory / f"{case['mode']}.cir", case["circuit"]["netlist"], output, limit)
                    write_json(directory / f"{case['mode']}-trace.json", case["circuit"]["trace"], output, limit)
            result = {"run_id": run_id, "method": method, "seed": seed, "proposals": state["proposals"],
                      "counts": state["counts"], "operations": state["operations"],
                      "invalid_reasons": state["invalid_reasons"],
                      "champion": state["champion"], "search_seconds": state["search_seconds"],
                      "assessment_seconds": assessment_seconds,
                      "cumulative_peak_worker_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                      "assessment": {name: value["summary"] for name, value in assessment.items()}}
            write_json(result_path, result, output, limit)
            print(f"Completed {method}/{seed}: {state['proposals']} proposals, train={state['champion']['record']['loss']:.6g}", flush=True)
        summary["status"] = "complete"
    except BaseException as exc:
        summary["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        summary["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        try:
            summary["os_threads"] = len(list(Path("/proc/self/task").iterdir()))
        except OSError:
            summary["os_threads"] = None
        write_json(output / "worker-summary.json", summary, output, limit)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "demo"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--deadline", type=float)
    parser.add_argument("--program", type=Path)
    parser.add_argument("--f1", type=float)
    parser.add_argument("--f2", type=float)
    parser.add_argument("--lock-fd", type=int)
    parser.add_argument("--invocation-id")
    args = parser.parse_args()
    # Read only stdlib configuration data before applying the requested cap.
    from .config import load_config
    cfg = load_config()
    if args.command == "run":
        cfg = json.loads((args.output / "manifest.json").read_text())["config"]
        if args.lock_fd is None:
            raise RuntimeError("Start experimental workers with the bounded launcher")
        os.fstat(args.lock_fd)
        fcntl.flock(args.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        apply_limits(cfg["worker_address_mib"])
        if args.command == "run":
            execute(args.output, args.deadline, args.invocation_id)
            return
    except BaseException as exc:
        if args.command == "run":
            from .storage import read_json, write_json
            path = args.output / "worker-summary.json"
            old = read_json(path) if path.exists() else {}
            if old.get("invocation_id") != args.invocation_id:
                write_json(path, {"status": "partial", "invocation_id": args.invocation_id,
                                  "failure": f"{type(exc).__name__}: {exc}",
                                  "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},
                           args.output, cfg["output_mib"] * 1024**2)
        raise
    if args.command == "demo":
        from .evaluation import Requirement, evaluate_case
        from .language import make_pset, parse
        tree = parse(args.program.read_text(), make_pset(cfg))
        case = evaluate_case(tree, Requirement(args.f1, args.f2), cfg["assessment_points"], cfg, details=True)
        print(json.dumps(case, indent=2))


if __name__ == "__main__":
    main()
