"""Summarize saved pilot outcomes and extract one illustrative conditional trace.

No searches or circuit simulations occur here. The GP/303 example is selected
post hoc to explain an executed conditional, not to estimate method performance.
"""

import argparse
import csv
import io
from pathlib import Path
import statistics

from evolved_circuits.storage import bytes_used, read_json, write_json, write_text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/m1"))
    args = parser.parse_args()
    root = args.output
    manifest = read_json(root / "manifest.json")
    cfg = manifest["config"]
    limit = cfg["output_mib"] * 1024**2
    results = {p.parent.name: read_json(p) for p in root.glob("*/result.json")}
    pairs = []
    for seed in cfg["seeds"]:
        if all(f"{method}_{seed}" in results for method in ("gp", "random")):
            gp, random = (results[f"{method}_{seed}"] for method in ("gp", "random"))
            pairs.append({"seed": seed,
                          "gp_interpolation": gp["assessment"]["interpolation"]["loss"],
                          "random_interpolation": random["assessment"]["interpolation"]["loss"],
                          "gp_minus_random": gp["assessment"]["interpolation"]["loss"] - random["assessment"]["interpolation"]["loss"]})
    effects = [p["gp_minus_random"] for p in pairs]
    aggregate = {}
    rows = []
    for method in cfg["methods"]:
        runs = [r for r in results.values() if r["method"] == method]
        if not runs: continue
        aggregate[method] = {"runs": len(runs), "proposals": sum(r["proposals"] for r in runs),
                             "training_loss": statistics.mean(r["champion"]["record"]["loss"] for r in runs),
                             **{s + "_loss": statistics.mean(r["assessment"][s]["loss"] for r in runs)
                                for s in ("dense_training", "interpolation", "extrapolation")},
                             "counts": {key: sum(r["counts"][key] for r in runs) for key in runs[0]["counts"]}}
        for r in sorted(runs, key=lambda r: r["seed"]):
            rows.append({"method": method, "seed": r["seed"], "proposals": r["proposals"],
                         "unique_candidates": r["counts"]["unique_candidates"],
                         "case_evaluations": r["counts"]["actual_case_evaluations"],
                         "invalid_proposal_cases": r["counts"]["proposal_invalid_cases"],
                         "training_loss": r["champion"]["record"]["loss"],
                         **{s + "_loss": r["assessment"][s]["loss"]
                            for s in ("dense_training", "interpolation", "extrapolation")},
                         "interpolation_lowpass_loss": r["assessment"]["interpolation"]["lowpass_loss"],
                         "interpolation_highpass_loss": r["assessment"]["interpolation"]["highpass_loss"],
                         "interpolation_successes": r["assessment"]["interpolation"]["successes"],
                         "tree_nodes": r["champion"]["record"]["tree_nodes"],
                         "training_mean_components": r["champion"]["record"]["mean_components"],
                         "search_seconds": r["search_seconds"], "assessment_seconds": r["assessment_seconds"],
                         "cumulative_peak_worker_rss_kib": r["cumulative_peak_worker_rss_kib"]})
    comparison = {"run_id": manifest["run_id"], "completed_runs": len(results),
                  "authorized_runs": len(cfg["methods"])*len(cfg["seeds"]),
                  "pairs": pairs, "aggregate": aggregate,
                  "mean_paired_difference": statistics.mean(effects) if effects else None,
                  "median_paired_difference": statistics.median(effects) if effects else None,
                  "gp_interpolation_wins": sum(x < 0 for x in effects),
                  "inference": "Three-seed descriptive pilot; no confirmatory test or interval"}
    write_json(root / "comparison.json", comparison, root, limit)
    if rows:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        write_text(root / "seed-results.csv", buffer.getvalue(), root, limit)
    example_path = root / "gp_303/assessment.json"
    if example_path.exists():
        example = read_json(example_path)["dense_training"]["cases"][:2]
        for case in example:
            if case["invalid"]: continue
            stem = root / f"gp_303/example-1000-{case['mode']}"
            write_text(stem.with_suffix(".cir"), case["circuit"]["netlist"], root, limit)
            write_json(stem.with_suffix(".json"), case, root, limit)
    print(f"Completed {len(results)} runs, {sum(r['proposals'] for r in results.values())} proposals.")
    print(f"Mean paired interpolation difference: {comparison['mean_paired_difference']}")
    print(f"Generated artifact bytes: {bytes_used(root)}")


if __name__ == "__main__":
    main()
