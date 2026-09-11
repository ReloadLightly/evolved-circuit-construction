"""Post-search assessment only: never imported by the selection module."""

from .evaluation import evaluate_case, requirements, summarize
from .language import make_pset, parse


def assess(state, cfg):
    if state["status"] != "searched" or state["proposals"] != cfg["proposals"]:
        raise ValueError("Assessment requires a completed, training-selected search")
    tree = parse(state["champion"]["program"], make_pset(cfg))
    bases = {"dense_training": cfg["training_b"],
             "interpolation": [1000 * 10**q for q in cfg["interpolation_q"]],
             "extrapolation": [1000 * 10**q for q in cfg["extrapolation_q"]]}
    result = {}
    for split, values in bases.items():
        cases = [evaluate_case(tree, req, cfg["assessment_points"], cfg, details=True)
                 for req in requirements(values, cfg["ratio"])]
        result[split] = {"summary": summarize(cases), "cases": cases}
    return result
