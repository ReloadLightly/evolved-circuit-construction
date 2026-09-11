"""Physics/construction fixtures only; none are search initialization seeds."""

import copy
import json
import math
import random
import subprocess
import sys

import numpy as np
import pytest

from evolved_circuits.circuit import Circuit, Edge, InvalidCircuit
from evolved_circuits.config import load_config
from evolved_circuits.evaluation import Requirement, TrainingEvaluator, grid, score_response
from evolved_circuits.language import develop, initial, legal, make_pset, parse, protected, typed, vary


@pytest.fixture
def cfg():
    return load_config()


def test_loaded_wire_divider_and_fixture(cfg):
    c = Circuit(cfg)
    c.add("W", 2, 3)
    c.add("W", 3, 4)
    frequencies = np.geomspace(100, 1e6, 81)
    np.testing.assert_allclose(c.response(frequencies), 0.5, rtol=1e-14)
    assert "Rsource n1 n2 1000" in c.netlist()
    assert "Rload n2 0 1000" in c.netlist()
    with pytest.raises(InvalidCircuit, match="fixture"):
        c.add("C", 1, 2, 1e-8)
    with pytest.raises(InvalidCircuit, match="fixture"):
        c.add("R", 2, 4, 10)


@pytest.mark.parametrize("kind,value", [("L", 0.02), ("C", 2e-8)])
def test_loaded_series_lc_closed_form(cfg, kind, value):
    c = Circuit(cfg)
    c.add(kind, 2, 3, value)
    c.add("W", 3, 4)
    f = np.geomspace(100, 1e6, 101)
    z = 2j*np.pi*f*value if kind == "L" else 1/(2j*np.pi*f*value)
    expected = cfg["load_ohm"] / (cfg["source_ohm"] + cfg["load_ohm"] + z)
    np.testing.assert_allclose(c.response(f), expected, rtol=1e-12, atol=1e-13)


def test_loaded_shunt_capacitor_and_lc_ladder(cfg):
    c = Circuit(cfg)
    c.add("W", 2, 3)
    c.add("W", 3, 4)
    cap, inductance = 3e-8, 0.015
    c.add("C", 4, 0, cap)
    f = np.geomspace(100, 1e6, 101)
    s = 2j*np.pi*f
    rs, rl = cfg["source_ohm"], cfg["load_ohm"]
    np.testing.assert_allclose(c.response(f), rl/(rs+rl+s*cap*rs*rl), rtol=1e-12, atol=1e-13)
    c.edges[0] = Edge("L", 2, 3, inductance)
    load_z = 1 / (1/rl + s*cap)
    np.testing.assert_allclose(c.response(f), load_z/(rs+s*inductance+load_z), rtol=1e-11, atol=1e-13)


def test_parallel_and_series_division_physics(cfg):
    p = make_pset(cfg)
    f = np.geomspace(100, 1e6, 81)
    parallel = develop(parse("Embryo(Parallel(C(0.0), C(0.0)), Wire)", p), 1000, 2000, cfg)
    series = develop(parse("Embryo(Series(L(0.0), L(0.0)), Wire)", p), 1000, 2000, cfg)
    np.testing.assert_allclose(parallel.response(f), 1000/(2000+1/(2j*np.pi*f*2e-8)), rtol=1e-11)
    np.testing.assert_allclose(series.response(f), 1000/(2000+2j*np.pi*f*2*10**-3.5), rtol=1e-11)


def test_disconnected_output_ground_short_and_floating_island(cfg):
    c = Circuit(cfg)
    np.testing.assert_array_equal(c.response([1000]), [0j])
    c.add("W", 2, 3)
    c.add("W", 3, 4)
    c.add("W", 4, 0)
    np.testing.assert_array_equal(c.response([1000]), [0j])
    floating = Circuit(cfg)
    a, b = floating.new_node(), floating.new_node()
    floating.add("L", a, b, 0.01)
    with pytest.raises(InvalidCircuit, match="floating"):
        floating.response([1000])


def test_singular_resonant_island_is_invalid(cfg):
    c = Circuit(cfg)
    # Dangling lossless parallel LC at exact resonance has undefined node voltage.
    # Binary-exact angular frequency and C*L make cancellation exact in float64.
    node = c.new_node()
    c.add("L", node, 0, 1.0)
    c.add("C", node, 0, 1e-4)
    with pytest.raises(InvalidCircuit, match="singular"):
        c.response([100/(2*np.pi)])


def test_lazy_conditional_only_chosen_branch_allocates(cfg):
    p = make_pset(cfg)
    limited = {**cfg, "max_components": 1, "max_circuit_nodes": 5}
    tree = parse("Embryo(If(pSub(pF2, pF1), L(vF1), Series(C(0.0), C(0.0))), Wire)", p)
    c = develop(tree, 1000, 2000, limited, trace=True)
    assert c.components == 1 and c.nodes == 5
    assert [x["operator"] for x in c.trace] == ["If", "L", "Wire"]
    with pytest.raises(InvalidCircuit, match="node_limit"):
        develop(tree, 2000, 1000, limited)
    zero = parse("Embryo(If(pSub(pF1, pF1), Open, Wire), Wire)", p)
    np.testing.assert_allclose(develop(zero, 1000, 2000, cfg).response([1000]), 0.5)


def test_ground_operators_and_short_component_count(cfg):
    p = make_pset(cfg)
    left = develop(parse("Embryo(GroundLeft(L(0.0), C(0.0)), Wire)", p), 1000, 2000, cfg)
    right = develop(parse("Embryo(GroundRight(L(0.0), C(0.0)), Wire)", p), 1000, 2000, cfg)
    assert left.edges[1].a == 2 and right.edges[1].a == 3
    short = develop(parse("Embryo(Parallel(L(0.0), Wire), Wire)", p), 1000, 2000, cfg)
    assert short.components == 1 and short.active_components() == 0
    np.testing.assert_allclose(short.response([1000]), 0.5)


def test_determinism_print_roundtrip_and_typed_variation(cfg):
    random.seed(852)
    p = make_pset(cfg)
    parent = initial(p, cfg)
    for _ in range(160):
        mate = initial(p, cfg)
        child, _, failures = vary(parent, mate, p, cfg)
        assert typed(child) and legal(child, cfg) and failures <= 2
        restored = parse(str(child), p)
        assert str(restored) == str(child)
        try:
            a = develop(child, 1000, 2000, cfg, trace=True).as_dict()
        except InvalidCircuit:
            pass
        else:
            assert a == develop(restored, 1000, 2000, cfg, trace=True).as_dict()
        parent = child
    with pytest.raises(ValueError, match="type"):
        parse("Embryo(L(pF1), Wire)", p)
    with pytest.raises(ValueError, match="type"):
        parse("Embryo(If(vF1, Wire, Open), Wire)", p)


def test_signed_protected_arithmetic_and_component_bounds(cfg):
    assert protected("Sub", [1, 2], cfg) == -1
    assert protected("Div", [-2, 0], cfg) == -2
    assert protected("Mul", [-1e6, 1e6], cfg) == -1e6
    p = make_pset(cfg)
    for value in [-1e300, -1e6, 0, 1e6, 1e300]:
        tree = parse(f"Embryo(L({value}), C({value}))", p)
        circuit = develop(tree, 1000, 2000, cfg)
        for e in circuit.edges:
            lo, hi = cfg["value_log10_bounds"][e.kind]
            assert math.isfinite(e.value) and 10**lo <= e.value <= 10**hi


def test_constructed_component_and_gp_limits(cfg):
    c = Circuit(cfg)
    for _ in range(12):
        c.add("L", 2, 3, 0.01)
    with pytest.raises(InvalidCircuit, match="component_limit"):
        c.add("L", 2, 3, 0.01)
    p = make_pset(cfg)
    text = "Wire"
    for _ in range(10):
        text = f"Series(Wire, {text})"
    with pytest.raises(InvalidCircuit, match="tree_limit"):
        develop(parse(f"Embryo({text}, Wire)", p), 1000, 2000, cfg)


def test_fixed_normalization_band_weights_and_clipping(cfg):
    req = Requirement(1000, 2000)
    f = np.array([100, 1000, 1500, 2000, 10000])
    score, _ = score_response(np.full(5, 0.5), f, req, cfg)
    assert score["loss"] == 0.5
    score, _ = score_response(np.zeros(5), f, req, cfg)
    assert score["loss"] == 0.5
    score, _ = score_response(np.array([0.5, 0.5, 1e99, 0, 0]), f, req, cfg)
    assert score["success"] and score["loss"] == 0 and score["clipped"] == 0
    score, _ = score_response(np.full(5, 1e300), f, req, cfg)
    assert score["loss"] == cfg["loss_clip"] and score["clipped"] == 4


def test_training_frozen_six_cases_and_exact_boundaries(cfg):
    evaluator = TrainingEvaluator(cfg)
    assert len(evaluator.requirements) == 6
    assert {(r.f1, r.f2) for r in evaluator.requirements} == {
        (1000, 2000), (2000, 1000), (10000, 20000), (20000, 10000), (100000, 200000), (200000, 100000)}
    for req in evaluator.requirements:
        f = grid(req, 81, cfg)
        assert req.f1 in f and req.f2 in f and 81 <= len(f) <= 83


def test_limit_is_applied_before_numpy_import():
    code = """
import sys, resource, os, json
from evolved_circuits.worker import apply_limits
assert 'numpy' not in sys.modules
apply_limits()
import numpy as np
print(json.dumps([resource.getrlimit(resource.RLIMIT_AS), os.environ['OPENBLAS_NUM_THREADS'], int(np.linalg.solve([[2.]], [2.])[0])]))
"""
    result = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True, timeout=20)
    cap, threads, solved = json.loads(result.stdout)
    assert cap == [768*1024**2, 768*1024**2] and threads == "1" and solved == 1
