"""One frozen configuration shared by development, scoring, and search."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_config(path=None):
    cfg = json.loads(Path(path or ROOT / "configs/m1.json").read_text())
    validate(cfg)
    return cfg


def validate(c):
    ceilings = {"max_components": 12, "max_circuit_nodes": 24,
                "max_gp_nodes": 127, "max_depth": 9, "wall_seconds": 1200,
                "worker_address_mib": 768, "output_mib": 100,
                "cache_records": 4096}
    for key, ceiling in ceilings.items():
        if not 0 < c[key] <= ceiling:
            raise ValueError(f"{key} must be in (0, {ceiling}]")
    if c["workers"] != 1 or c["blas_threads"] != 1:
        raise ValueError("Exactly one worker and one BLAS thread required")
    if not 0 < c["population"] <= c["proposals"] <= 384:
        raise ValueError("M1 requires a finite budget of at most 384 per run")
    if c["proposals"] % c["population"]:
        raise ValueError("Proposal budget must contain whole populations")
    if not 0 < c["elites"] < c["population"]:
        raise ValueError("Elites must leave room for offspring")
    if c["variation_attempts"] != 2:
        raise ValueError("Exactly two bounded variation attempts")
    if not 0 <= c["initial_depth"][0] <= c["initial_depth"][1] <= 3:
        raise ValueError("Initial branch depth must be at most 3 (65 total nodes)")
    if not 0 <= c["mutation_depth"][0] <= c["mutation_depth"][1] <= 3:
        raise ValueError("Mutation subtree depth must be at most 3")


def identity(c):
    """Hash numerical/search code and exact config; reports/tests are not search code."""
    digest = hashlib.sha256(json.dumps(c, sort_keys=True).encode())
    for path in sorted((ROOT / "src/evolved_circuits").glob("*.py")):
        if path.name != "plotting.py":
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()
