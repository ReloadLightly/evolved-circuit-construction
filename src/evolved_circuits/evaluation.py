"""Training-only evaluator and shared electrical scoring equations."""

from collections import Counter, OrderedDict
from dataclasses import dataclass

import numpy as np

from .circuit import InvalidCircuit
from .language import develop


@dataclass(frozen=True)
class Requirement:
    f1: float
    f2: float

    @property
    def mode(self):
        return "lowpass" if self.f1 < self.f2 else "highpass"


def requirements(bases, ratio):
    return [Requirement(*pair) for b in bases for pair in [(b, ratio*b), (ratio*b, b)]]


def grid(req, points, cfg):
    return np.unique(np.r_[np.geomspace(*cfg["frequency_hz"], points), req.f1, req.f2])


def masks(req, frequencies):
    if req.f1 < req.f2:
        return frequencies <= req.f1, frequencies >= req.f2
    return frequencies >= req.f1, frequencies <= req.f2


def score_response(response, frequencies, req, cfg):
    amplitude = np.abs(response) / cfg["normalization"]
    if not np.all(np.isfinite(amplitude)):
        raise InvalidCircuit("nonfinite_amplitude")
    passing, stopping = masks(req, frequencies)
    if not np.any(passing) or not np.any(stopping):
        raise ValueError("Empty scored band")
    # Clip residual magnitude before squaring; equivalent to clipping squared error.
    pe, se = np.abs(amplitude[passing] - 1), amplitude[stopping]
    limit = np.sqrt(cfg["loss_clip"])
    loss = 0.5 * np.mean(np.minimum(pe, limit)**2) + 0.5 * np.mean(np.minimum(se, limit)**2)
    return {"loss": float(loss), "invalid": 0,
            "clipped": int(np.sum(pe > limit) + np.sum(se > limit)),
            "scored_points": int(np.sum(passing) + np.sum(stopping)),
            "success": bool(np.all(pe <= cfg["pass_tolerance"]) and np.all(se <= cfg["stop_tolerance"]))}, amplitude


def evaluate_case(tree, req, points, cfg, details=False):
    frequencies = grid(req, points, cfg)
    attempted_solve = 0
    try:
        circuit = develop(tree, req.f1, req.f2, cfg, trace=details)
        attempted_solve = 1
        response = circuit.response(frequencies)
        result, amplitude = score_response(response, frequencies, req, cfg)
        result.update(components=circuit.active_components(), created_components=circuit.components)
        if details:
            result.update(circuit=circuit.as_dict(), frequency_hz=frequencies.tolist(), amplitude=amplitude.tolist())
    except InvalidCircuit as exc:
        result = {"loss": cfg["invalid_loss"], "invalid": 1, "reason": str(exc),
                  "clipped": 0, "scored_points": 0, "success": False,
                  "components": cfg["max_components"] + 1, "created_components": 0}
    result.update(f1=req.f1, f2=req.f2, mode=req.mode, solver_calls=attempted_solve)
    return result


def summarize(cases):
    return {"loss": float(np.mean([c["loss"] for c in cases])),
            "lowpass_loss": float(np.mean([c["loss"] for c in cases if c["mode"] == "lowpass"])),
            "highpass_loss": float(np.mean([c["loss"] for c in cases if c["mode"] == "highpass"])),
            "cases": len(cases), "invalid_cases": sum(c["invalid"] for c in cases),
            "clipped_points": sum(c["clipped"] for c in cases),
            "scored_points": sum(c["scored_points"] for c in cases),
            "successes": sum(c["success"] for c in cases),
            "mean_components": float(np.mean([c["components"] for c in cases])),
            "solver_calls": sum(c["solver_calls"] for c in cases),
            "invalid_reasons": dict(Counter(c["reason"] for c in cases if c["invalid"]))}


def fitness_key(record):
    return record["loss"], record["mean_components"], record["tree_nodes"]


class TrainingEvaluator:
    """No assessment API or held-out requirements are passed to selection."""
    def __init__(self, cfg, cache=()):
        self.cfg = cfg
        self.requirements = requirements(cfg["training_b"], cfg["ratio"])
        self.cache = OrderedDict(cache)

    def evaluate(self, tree):
        key = str(tree)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key], False
        cases = [evaluate_case(tree, req, self.cfg["training_points"], self.cfg) for req in self.requirements]
        record = summarize(cases)
        record["tree_nodes"] = len(tree)
        self.cache[key] = record
        if len(self.cache) > self.cfg["cache_records"]:
            self.cache.popitem(last=False)
        return record, True
