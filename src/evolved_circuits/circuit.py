"""Passive nodal AC analysis, with exact ideal-wire contraction."""

from dataclasses import dataclass
import math

import numpy as np


class InvalidCircuit(ValueError): pass


@dataclass(frozen=True)
class Edge:
    kind: str
    a: int
    b: int
    value: float = 0.0


class Circuit:
    # Logical fixture nodes: 0 ground, 1 source, 2 input, 3 embryo middle, 4 output.
    def __init__(self, cfg):
        self.cfg = cfg
        self.edges = []
        self.nodes = 5
        self.components = 0
        self.trace = []

    def new_node(self):
        if self.nodes >= self.cfg["max_circuit_nodes"]:
            raise InvalidCircuit("circuit_node_limit")
        node = self.nodes
        self.nodes += 1
        return node

    def add(self, kind, a, b, value=0.0):
        if kind not in ("W", "L", "C") or 1 in (a, b):
            raise InvalidCircuit("fixture_modification")
        if not all(0 <= n < self.nodes for n in (a, b)):
            raise InvalidCircuit("unknown_node")
        if kind != "W":
            lo, hi = self.cfg["value_log10_bounds"][kind]
            if not math.isfinite(value) or not 10**lo <= value <= 10**hi:
                raise InvalidCircuit("component_value")
            if self.components >= self.cfg["max_components"]:
                raise InvalidCircuit("component_limit")
            self.components += 1
        self.edges.append(Edge(kind, a, b, value))

    def contracted(self):
        roots = list(range(self.nodes))
        def root(n):
            while roots[n] != n:
                roots[n] = roots[roots[n]]
                n = roots[n]
            return n
        for edge in self.edges:
            if edge.kind == "W":
                a, b = root(edge.a), root(edge.b)
                roots[max(a, b)] = min(a, b)
        labels = [root(i) for i in range(self.nodes)]
        edges = [Edge(e.kind, labels[e.a], labels[e.b], e.value)
                 for e in self.edges if e.kind != "W" and labels[e.a] != labels[e.b]]
        return labels, edges

    def active_components(self):
        return len(self.contracted()[1])

    def response(self, frequencies):
        frequencies = np.asarray(frequencies, dtype=float)
        if not np.all(np.isfinite(frequencies) & (frequencies > 0)):
            raise ValueError("AC frequencies must be positive and finite")
        labels, edges = self.contracted()
        ground, source, inp, _, output = labels[:5]
        edges += [Edge("R", source, inp, self.cfg["source_ohm"]),
                  Edge("R", output, ground, self.cfg["load_ohm"])]
        used = {n for e in edges for n in (e.a, e.b)} | {output}
        # A floating connected island makes its node potentials undefined. No gmin.
        reachable = {ground, source}
        while True:
            expanded = reachable | {n for e in edges if e.a in reachable or e.b in reachable for n in (e.a, e.b)}
            if expanded == reachable: break
            reachable = expanded
        if used - reachable:
            raise InvalidCircuit("floating_island")
        unknown = sorted(used - {ground, source})
        positions = {n: i for i, n in enumerate(unknown)}
        n = len(unknown)
        mat = np.zeros((len(frequencies), n, n), dtype=complex)
        rhs = np.zeros((len(frequencies), n), dtype=complex)
        omega = 2j * np.pi * frequencies
        for e in edges:
            if e.a == e.b: continue
            y = 1 / e.value if e.kind == "R" else (omega * e.value if e.kind == "C" else 1 / (omega * e.value))
            for a, b in ((e.a, e.b), (e.b, e.a)):
                if a not in positions: continue
                i = positions[a]
                mat[:, i, i] += y
                if b in positions:
                    mat[:, i, positions[b]] -= y
                elif b == source:
                    rhs[:, i] += y * self.cfg["source_v"]
        if n:
            # Row scaling is algebraically exact, not regularization.
            scale = np.max(np.abs(mat), axis=2)
            if np.any(scale == 0):
                raise InvalidCircuit("singular")
            mat = mat / scale[:, :, None]
            rhs = rhs / scale
            try:
                with np.errstate(all="raise"):
                    volts = np.linalg.solve(mat, rhs[..., None])[..., 0]
                    residual = np.max(np.abs(np.einsum("fij,fj->fi", mat, volts) - rhs), axis=1)
                    tolerance = 1e-8 * (1 + np.max(np.abs(volts), axis=1))
                    if not np.all(np.isfinite(volts)) or np.any(residual > tolerance):
                        raise InvalidCircuit("nonfinite_or_residual")
            except (np.linalg.LinAlgError, FloatingPointError) as exc:
                raise InvalidCircuit("singular_or_nonfinite") from exc
        if output == ground:
            return np.zeros(len(frequencies), dtype=complex)
        if output == source:
            return np.ones(len(frequencies), dtype=complex)
        return volts[:, positions[output]] / self.cfg["source_v"]

    def netlist(self):
        labels, edges = self.contracted()
        ground, source, inp, _, output = labels[:5]
        def name(n): return "0" if n == ground else f"n{n}"
        lines = ["* Developed passive network; wires contracted",
                 f"* Vout = {name(output)}; logical fixture source/load preserved",
                 f"Vsource {name(source)} 0 AC {self.cfg['source_v']:.17g}",
                 f"Rsource {name(source)} {name(inp)} {self.cfg['source_ohm']:.17g}",
                 f"Rload {name(output)} 0 {self.cfg['load_ohm']:.17g}"]
        for i, e in enumerate(edges, 1):
            lines.append(f"{e.kind}{i} {name(e.a)} {name(e.b)} {e.value:.17g}")
        lines += [".ac dec 100 100 1000000", ".end"]
        return "\n".join(lines) + "\n"

    def as_dict(self):
        from dataclasses import asdict
        return {"allocated_nodes": self.nodes, "created_components": self.components,
                "active_components": self.active_components(),
                "edges": [asdict(e) for e in self.edges], "trace": self.trace,
                "netlist": self.netlist()}
