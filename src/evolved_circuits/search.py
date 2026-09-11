"""Equal proposal accounting for GP and independent random search."""

import hashlib
import random
import time
from collections import Counter
from copy import deepcopy

from deap import base, gp, tools

from .evaluation import TrainingEvaluator, fitness_key
from .language import initial, make_pset, parse, vary


class DeadlineReached(RuntimeError): pass


class MinimizingFitness(base.Fitness):
    weights = (-1.0, -1.0, -1.0)


class Individual(gp.PrimitiveTree):
    def __init__(self, nodes, record):
        super().__init__(nodes)
        self.record = record
        self.fitness = MinimizingFitness(fitness_key(record))


def tuple_state(value):
    return tuple(tuple_state(x) for x in value) if isinstance(value, (list, tuple)) else value


def fresh_state(method, seed, run_id):
    random.seed(seed)
    return {"run_id": run_id, "method": method, "seed": seed, "status": "searching",
            "proposals": 0, "generation": 0, "population": [], "offspring": [],
            "champion": None, "pending": None, "history": [], "seen": [],
            "cache": [], "rng": random.getstate(), "search_seconds": 0.0,
            "counts": {"unique_candidates": 0, "fitness_computations": 0,
                       "actual_case_evaluations": 0, "actual_solver_calls": 0,
                       "proposal_invalid_cases": 0, "computed_invalid_cases": 0,
                       "proposal_clipped_points": 0, "computed_clipped_points": 0,
                       "variation_failures": 0}, "operations": {}, "invalid_reasons": {}}


def run_search(cfg, method, seed, run_id, save, deadline, state=None):
    """Save each completed generation and any cooperative/exception partial state."""
    if method not in ("gp", "random"):
        raise ValueError(method)
    state = deepcopy(state) if state is not None else fresh_state(method, seed, run_id)
    if (state["run_id"], state["method"], state["seed"]) != (run_id, method, seed):
        raise ValueError("Incompatible checkpoint")
    if state["status"] == "searched":
        return state
    random.setstate(tuple_state(state["rng"]))
    pset = make_pset(cfg)
    evaluator = TrainingEvaluator(cfg, state["cache"])
    seen = set(state["seen"])
    started = time.monotonic()
    previous_seconds = state["search_seconds"]

    def snapshot():
        state["rng"] = random.getstate()
        state["cache"] = list(evaluator.cache.items())
        state["seen"] = sorted(seen)
        state["counts"]["unique_candidates"] = len(seen)
        state["search_seconds"] = previous_seconds + time.monotonic() - started
        save(state)

    try:
        while state["proposals"] < cfg["proposals"] or state["pending"]:
            if time.monotonic() >= deadline:
                raise DeadlineReached("Batch deadline reached; checkpoint retained")
            if state["pending"] is None:
                failures = 0
                if method == "random" or not state["population"]:
                    child = initial(pset, cfg)
                    operation = "initial" if state["generation"] == 0 else "random"
                else:
                    population = [Individual(parse(x["program"], pset), x["record"]) for x in state["population"]]
                    parent, mate = tools.selTournament(population, 2, tournsize=cfg["tournament"])
                    child, operation, failures = vary(parent, mate, pset, cfg)
                state["pending"] = str(child)
                state["proposals"] += 1
                seen.add(hashlib.sha256(str(child).encode()).hexdigest())
                state["counts"]["variation_failures"] += failures
                state["operations"][operation] = state["operations"].get(operation, 0) + 1
            child = parse(state["pending"], pset)
            record, computed = evaluator.evaluate(child)
            counts = state["counts"]
            counts["proposal_invalid_cases"] += record["invalid_cases"]
            counts["proposal_clipped_points"] += record["clipped_points"]
            if computed:
                counts["fitness_computations"] += 1
                counts["actual_case_evaluations"] += record["cases"]
                counts["actual_solver_calls"] += record["solver_calls"]
                counts["computed_invalid_cases"] += record["invalid_cases"]
                counts["computed_clipped_points"] += record["clipped_points"]
                state["invalid_reasons"] = dict(Counter(state["invalid_reasons"]) + Counter(record["invalid_reasons"]))
            item = {"program": str(child), "record": record}
            state["offspring"].append(item)
            if state["champion"] is None or fitness_key(record) < fitness_key(state["champion"]["record"]):
                state["champion"] = item
            state["pending"] = None
            if len(state["offspring"]) == cfg["population"]:
                key = lambda x: fitness_key(x["record"])
                if method == "gp" and state["population"]:
                    state["population"] = sorted(state["population"], key=key)[:cfg["elites"]] + sorted(state["offspring"], key=key)[:cfg["population"]-cfg["elites"]]
                else:
                    state["population"] = sorted(state["offspring"], key=key)
                state["offspring"] = []
                state["history"].append({"generation": state["generation"], "proposals": state["proposals"],
                                         "best_training_loss": state["champion"]["record"]["loss"],
                                         "population_best_loss": min(x["record"]["loss"] for x in state["population"]),
                                         "unique_candidates": len(seen)})
                state["generation"] += 1
                snapshot()
        state["status"] = "searched"
        snapshot()
    except BaseException:
        snapshot()
        raise
    return state
