"""Typed DEAP trees interpreted lazily; no gp.compile/eager side effects."""

import ast
import math
import random
from functools import partial

from deap import gp


class Program: pass
class Build: pass
class Value: pass
class Predicate: pass


def _not_executable(*args):
    raise RuntimeError("Use the lazy developmental interpreter")


def make_pset(cfg):
    p = gp.PrimitiveSetTyped("Circuit", [], Program)
    for name, args, result in [
        ("Embryo", [Build, Build], Program),
        ("L", [Value], Build), ("C", [Value], Build),
        ("Series", [Build, Build], Build),
        ("Parallel", [Build, Build], Build),
        ("GroundLeft", [Build, Build], Build),
        ("GroundRight", [Build, Build], Build),
        ("If", [Predicate, Build, Build], Build),
    ]:
        p.addPrimitive(_not_executable, args, result, name=name)
    p.addTerminal("wire", Build, name="Wire")
    p.addTerminal("open", Build, name="Open")
    for prefix, typ in [("v", Value), ("p", Predicate)]:
        for op in ["Add", "Sub", "Mul", "Div"]:
            p.addPrimitive(_not_executable, [typ, typ], typ, name=prefix + op)
        p.addPrimitive(_not_executable, [typ], typ, name=prefix + "Neg")
        for name in ["F1", "F2"]:
            p.addTerminal(name, typ, name=prefix + name)
        p.addEphemeralConstant(prefix + "Const", partial(random.uniform, *cfg["constant_range"]), typ)
    return p


def typed(tree):
    pending = [Program]
    for node in tree:
        if not pending or node.ret is not pending.pop():
            return False
        if node.arity:
            pending.extend(reversed(node.args))
    return not pending


def legal(tree, cfg):
    return typed(tree) and len(tree) <= cfg["max_gp_nodes"] and tree.height <= cfg["max_depth"]


def parse(text, pset):
    """Read our printed trees without eval; numerical literals inherit context type."""
    def walk(node, typ):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            prim = pset.mapping[node.func.id]
            if prim.ret is not typ or len(node.args) != prim.arity:
                raise ValueError("Wrong primitive type/arity")
            out = [prim]
            for arg, expected in zip(node.args, prim.args):
                out.extend(walk(arg, expected))
            return out
        if isinstance(node, ast.Name):
            term = pset.mapping[node.id]
            if term.ret is not typ or term.arity:
                raise ValueError("Wrong terminal type")
            return [term]
        if typ in (Value, Predicate):
            value = ast.literal_eval(node)
            if not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError("Nonfinite/non-numeric constant")
            return [gp.Terminal(float(value), False, typ)]
        raise ValueError("Malformed tree")
    tree = gp.PrimitiveTree(walk(ast.parse(text, mode="eval").body, Program))
    if not typed(tree):
        raise ValueError("Ill-typed program")
    return tree


def initial(pset, cfg):
    # Independent half-and-half branches on the two original modifiable edges.
    # Branch depth <=3 gives at most 65 nodes, including the Embryo root.
    # No rejection sampling or hidden extra initial proposals.
    nodes = [pset.mapping["Embryo"]]
    for _ in range(2):
        nodes += gp.genHalfAndHalf(pset, *cfg["initial_depth"], type_=Build)
    return gp.PrimitiveTree(nodes)


def vary(parent, mate, pset, cfg):
    mode = random.random()
    if mode >= cfg["crossover"] + cfg["mutation"]:
        return gp.PrimitiveTree(parent), "reproduction", 0
    operation = "crossover" if mode < cfg["crossover"] else (
        "constant" if random.random() < cfg["constant_mutation_fraction"] else "subtree")
    for attempt in range(cfg["variation_attempts"]):
        child = gp.PrimitiveTree(parent)
        if operation == "crossover":
            child, _ = gp.cxOnePoint(child, gp.PrimitiveTree(mate))
        elif operation == "subtree":
            # Root mutation must still produce a two-branch embryo.
            def expr(pset, type_):
                if type_ is Program:
                    return list(initial(pset, cfg))
                return gp.genGrow(pset, *cfg["mutation_depth"], type_=type_)
            child, = gp.mutUniform(child, expr, pset)
        else:
            choices = [i for i, n in enumerate(child)
                       if not n.arity and n.ret in (Value, Predicate)
                       and isinstance(n.value, (int, float))]
            if choices:
                i = random.choice(choices)
                value = child[i].value + random.gauss(0, cfg["constant_sigma"])
                child[i] = gp.Terminal(max(-cfg["expression_bound"], min(cfg["expression_bound"], value)), False, child[i].ret)
        if legal(child, cfg):
            return child, operation, attempt
    return gp.PrimitiveTree(parent), "fallback", cfg["variation_attempts"]


def protected(op, args, cfg):
    bound = cfg["expression_bound"]
    if op == "Add": value = args[0] + args[1]
    elif op == "Sub": value = args[0] - args[1]
    elif op == "Mul": value = args[0] * args[1]
    elif op == "Div": value = args[0] if abs(args[1]) < cfg["division_epsilon"] else args[0] / args[1]
    elif op == "Neg": value = -args[0]
    else: raise ValueError(op)
    return max(-bound, min(bound, value))


def develop(tree, f1, f2, cfg, trace=False):
    from .circuit import Circuit, InvalidCircuit
    if not legal(tree, cfg):
        raise InvalidCircuit("tree_limit_or_type")
    if not (math.isfinite(f1) and math.isfinite(f2) and f1 > 0 and f2 > 0 and f1 != f2):
        raise ValueError("Positive distinct finite requirements required")
    circuit = Circuit(cfg)
    # Prefix-tree child indices let us jump over the entire unchosen branch.
    children = {}
    def index(i):
        next_i = i + 1
        children[i] = []
        for _ in range(tree[i].arity):
            children[i].append(next_i)
            next_i = index(next_i)
        return next_i
    index(0)
    inputs = {"F1": math.log10(f1 / 1000.0), "F2": math.log10(f2 / 1000.0)}
    def number(i):
        node = tree[i]
        if not node.arity:
            return inputs[node.name[1:]] if node.name in ("vF1", "vF2", "pF1", "pF2") else float(node.value)
        return protected(node.name[1:], [number(j) for j in children[i]], cfg)
    def build(i, a, b):
        node = tree[i]
        args = children[i]
        event = {"tree_index": i, "operator": node.name, "site": [a, b]}
        if trace:
            circuit.trace.append(event)
        if node.name == "If":
            value = number(args[0])
            event.update(predicate=value, chosen="then" if value > 0 else "else")
            build(args[1] if value > 0 else args[2], a, b)
        elif node.name in ("L", "C"):
            x = number(args[0])
            lo, hi = cfg["value_log10_bounds"][node.name]
            value = 10.0 ** max(lo, min(hi, cfg["value_log10_offsets"][node.name] + x))
            circuit.add(node.name, a, b, value)
            event.update(expression=x, value=value)
        elif node.name == "Wire":
            circuit.add("W", a, b)
        elif node.name == "Open":
            pass
        elif node.name == "Series":
            mid = circuit.new_node()
            event["new_node"] = mid
            build(args[0], a, mid)
            build(args[1], mid, b)
        elif node.name == "Parallel":
            build(args[0], a, b)
            build(args[1], a, b)
        elif node.name in ("GroundLeft", "GroundRight"):
            build(args[0], a, b)
            build(args[1], a if node.name == "GroundLeft" else b, 0)
        else:
            raise ValueError(node.name)
    build(children[0][0], 2, 3)
    build(children[0][1], 3, 4)
    return circuit
