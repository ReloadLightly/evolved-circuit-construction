"""Small, unscored correctness fixtures for search accounting and continuation."""

import copy
import json
import time

import pytest

from evolved_circuits.assessment import assess
from evolved_circuits.config import identity, load_config, validate
from evolved_circuits.evaluation import TrainingEvaluator
from evolved_circuits.language import make_pset, parse
from evolved_circuits.search import DeadlineReached, run_search
from evolved_circuits.storage import write_json


@pytest.fixture
def cfg():
    return {**load_config(), "population": 4, "proposals": 12, "elites": 2}


@pytest.mark.parametrize("method", ["gp", "random"])
def test_duplicate_invalid_proposal_accounting_and_generation_checkpoints(cfg, monkeypatch, method):
    import evolved_circuits.search as search
    invalid = parse("Embryo(Series(Wire, Series(Wire, Wire)), Wire)", make_pset(cfg))
    cfg["max_depth"] = 1
    monkeypatch.setattr(search, "initial", lambda *args: invalid)
    monkeypatch.setattr(search, "vary", lambda *args: (invalid, "fallback", 2))
    checkpoints = []
    state = run_search(cfg, method, 101, "fixture", lambda s: checkpoints.append(copy.deepcopy(s)), time.monotonic()+10)
    assert state["proposals"] == 12
    assert state["counts"]["unique_candidates"] == 1
    assert state["counts"]["fitness_computations"] == 1
    assert state["counts"]["actual_case_evaluations"] == 6
    assert state["counts"]["actual_solver_calls"] == 0
    assert state["counts"]["proposal_invalid_cases"] == 72
    assert state["counts"]["computed_invalid_cases"] == 6
    assert [h["proposals"] for h in state["history"]] == [4, 8, 12]
    assert len(checkpoints) == 4
    assert len(state["population"]) == 4


@pytest.mark.parametrize("method", ["gp", "random"])
def test_mid_generation_resume_matches_uninterrupted_search(cfg, method):
    # A deterministic artificial deadline interrupts before the first proposal;
    # generation replay is also tested from a saved interior checkpoint.
    snapshots = []
    full = run_search(cfg, method, 202, "fixture", lambda s: snapshots.append(copy.deepcopy(s)), time.monotonic()+15)
    resumed = run_search(cfg, method, 202, "fixture", lambda s: None, time.monotonic()+15,
                         json.loads(json.dumps(snapshots[0])))
    for key in ["champion", "history", "counts", "operations", "rng", "population"]:
        assert resumed[key] == full[key]
    partial = []
    with pytest.raises(DeadlineReached):
        run_search(cfg, method, 202, "fixture", lambda s: partial.append(copy.deepcopy(s)), time.monotonic()-1)
    assert partial[-1]["proposals"] == 0
    with pytest.raises(ValueError, match="Incompatible"):
        run_search(cfg, method, 202, "different", lambda s: None, time.monotonic()+1, snapshots[0])


def test_true_partial_generation_resume_preserves_rng_and_slots(cfg, monkeypatch):
    original = TrainingEvaluator.evaluate
    calls = 0
    def interrupted(self, tree):
        nonlocal calls
        calls += 1
        if calls == 6:
            raise DeadlineReached("Artificial interruption before evaluation")
        return original(self, tree)
    full = run_search(cfg, "gp", 303, "fixture", lambda s: None, time.monotonic()+15)
    monkeypatch.setattr(TrainingEvaluator, "evaluate", interrupted)
    snapshots = []
    with pytest.raises(DeadlineReached):
        run_search(cfg, "gp", 303, "fixture", lambda s: snapshots.append(copy.deepcopy(s)), time.monotonic()+15)
    assert snapshots[-1]["proposals"] == 6 and snapshots[-1]["pending"] is not None
    monkeypatch.setattr(TrainingEvaluator, "evaluate", original)
    resumed = run_search(cfg, "gp", 303, "fixture", lambda s: None, time.monotonic()+15,
                         json.loads(json.dumps(snapshots[-1])))
    for key in ["champion", "history", "counts", "operations", "rng", "population"]:
        assert resumed[key] == full[key]


def test_heldout_changes_cannot_affect_selection(cfg, monkeypatch):
    import evolved_circuits.assessment as assessment
    monkeypatch.setattr(assessment, "assess", lambda *args: pytest.fail("Search called assessment"))
    modified = {**cfg, "interpolation_q": [99.0], "extrapolation_q": [-99.0], "assessment_points": 3}
    first = run_search(cfg, "gp", 101, "fixture", lambda s: None, time.monotonic()+15)
    second = run_search(modified, "gp", 101, "fixture", lambda s: None, time.monotonic()+15)
    for key in ["champion", "history", "counts", "rng"]:
        assert first[key] == second[key]
    first["status"] = "searching"
    with pytest.raises(ValueError, match="completed"):
        assess(first, cfg)


def test_equal_initial_prior_and_elitism(cfg):
    snapshots = {}
    for method in ["gp", "random"]:
        saved = []
        state = run_search(cfg, method, 101, "fixture", lambda s: saved.append(copy.deepcopy(s)), time.monotonic()+15)
        snapshots[method] = saved[0]
        losses = [h["best_training_loss"] for h in state["history"]]
        assert losses == sorted(losses, reverse=True)
    assert snapshots["gp"]["population"] == snapshots["random"]["population"]
    assert snapshots["gp"]["rng"] == snapshots["random"]["rng"]


def test_bounded_variation_fallback_consumes_slot(cfg, monkeypatch):
    import evolved_circuits.language as language
    parent = parse("Embryo(L(0.0), Wire)", make_pset(cfg))
    deep = "Wire"
    for _ in range(12): deep = f"Series(Wire, {deep})"
    oversized = parse(f"Embryo({deep}, Wire)", make_pset(cfg))
    monkeypatch.setattr(language.random, "random", lambda: 0.0)
    attempts = []
    def crossover(*args):
        attempts.append(1)
        return oversized, oversized
    monkeypatch.setattr(language.gp, "cxOnePoint", crossover)
    child, operation, failures = language.vary(parent, parent, make_pset(cfg), cfg)
    assert str(child) == str(parent) and operation == "fallback" and failures == len(attempts) == 2


def test_output_ceiling_and_config_limits(cfg, tmp_path):
    with pytest.raises(RuntimeError, match="ceiling"):
        write_json(tmp_path / "checkpoint.json", {"data": "x"*100}, tmp_path, 20)
    assert not list(tmp_path.iterdir())
    for key, value in [("workers", 2), ("max_components", 13), ("worker_address_mib", 769), ("proposals", 100000)]:
        with pytest.raises(ValueError):
            validate({**cfg, key: value})
    changed = {**cfg, "loss_clip": 100}
    assert identity(cfg) != identity(changed)
