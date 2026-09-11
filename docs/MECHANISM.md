# M1 implemented mechanism and reconstruction choices

Recorded before the first pilot search on 2026-09-11 UTC (2026-09-12 local).
The frozen numerical configuration is [configs/m1.json](../configs/m1.json).
The six training requirements, assessment splits, loss, seeds, proposal budget,
and engineering success criterion are unchanged from EXPERIMENT.md.

## Source-to-mechanism correspondence

The [conditional-filter paper, sections 2 and 4](https://www.genetic-programming.com/jkpdf/eh2000parameterizedfilter.pdf)
motivates an embryo embedded in a fixed source/load fixture, construction trees,
free variables in numerical subtrees, and a developmental conditional that executes
exactly one branch. M1 implements these mechanisms. Historical settings and results
are not measurements from this repository.

The [circuit-synthesis manuscript, section 4](https://www.genetic-programming.com/jkpdf/cmame.pdf)
describes component creation, topology modification, and development control.
M1 reconstructs a smaller grounded series/parallel graph language; it does not
copy the historical operators' full writing-head semantics. There are no
automatically defined functions, arbitrary distant-node joins, component polarity
operations, active components, or filter macros.

The [official DEAP GP tutorial](https://deap.readthedocs.io/en/master/tutorials/advanced/gp.html)
and [operator reference](https://deap.readthedocs.io/en/master/api/tools.html)
support typed trees, half-and-half initialization, compatible subtree crossover,
uniform subtree mutation and tournament selection. M1 uses these installed DEAP
APIs, with its own lazy interpreter instead of compiling side-effecting branches
as eager Python function arguments.

## Executable grammar

`Embryo(A, B)` develops the original modifiable wires `(2,3)` and `(3,4)`.
Node 0 is ground, 1 is the ideal voltage source, 2 is the fixture input,
3 is the original middle node, and 4 is the output probe. Every subtree receives
a construction site `(a,b)` representing a wire to replace.

| Operator | Effect on the current site |
|---|---|
| `Wire` | Finish the site as an ideal wire, merged exactly before analysis. |
| `Open` | Finish with no edge; this is an ordinary open, not historical SAFE_CUT. |
| `L(x)`, `C(x)` | Finish with one bounded positive inductor/capacitor. |
| `Series(A,B)` | Allocate node n; develop A on `(a,n)`, then B on `(n,b)`. |
| `Parallel(A,B)` | Develop A and B on the same `(a,b)` endpoints. |
| `GroundLeft(A,G)` | Develop A on `(a,b)` and G on `(a,0)`. |
| `GroundRight(A,G)` | Develop A on `(a,b)` and G on `(b,0)`. |
| `If(p,A,B)` | Evaluate p; develop A if p > 0, otherwise B. The other subtree has no effects. |

The source and load are added by the evaluator, outside the grammar. Candidates
can short their own nodes to ground but cannot replace or delete fixture elements.
Node/resource allocation is deterministic and counts only executed branches.
All created L/C components count toward the hard 12-component cap. The tie-break
counts components remaining after ideal-wire contraction removes shorted L/C edges,
averaged over the six training cases, then total genotype nodes. This is the
definition of **active components** here; it is not a full electrical redundancy
minimizer. The 24-node cap counts all allocated nodes, including the five fixture
labels and subsequently unused nodes.

The `p` and `v` numerical types have disjoint primitive sets and terminals. Each
supports Add, Sub, Mul, Div and Neg, plus F1/F2 and numerical constants. Inputs are
`log10(F1/1000)` and `log10(F2/1000)`. Division by a denominator with magnitude below
1e-12 returns its numerator. Arithmetic results saturate to [-1e6,1e6], preserving
sign. No conversion connects predicate and value expression types; future sizing
ablations can remove only the vF1/vF2 terminals. Those ablations are not implemented
or run in M1.

For component kind k, the value is `10**clip(offset[k] + x, lo[k], hi[k])`:
L offset -3.5, log bounds [-8,1]; C offset -8, log bounds [-12,-4]. Constants start
uniformly in [-4,4]; constant mutation adds N(0,1) with saturation to [-1e6,1e6].
These centers/ranges are reconstruction choices, not historical defaults.
Frequency dependence must be expressed by evolved arithmetic. There is no
external inverse-frequency scaling or mode-dependent circuit dispatch.

Each initial embryo branch independently uses DEAP half-and-half, with target
depth uniformly 0..3 and uniform primitive/terminal choices within each type.
Thus an initial program has at most 65 nodes and depth 4. Before execution, a
read-only review identified that an initially drafted 0..4 depth prior could
materialize 161 nodes; the missing prior constant was set to 0..3 before any pilot
data existed. This does not change the predeclared split, loss, seeds or budget.
Mutation subtrees use grow depth 0..3; root mutation regenerates an embryo. Variation
may propose an over-limit temporary tree; after at most two attempts to obtain a
legal tree it copies the selected parent and still charges one proposal. A
constant mutation with no numerical constant copies the parent. Compatible
crossover returns one child; its second result is discarded. Selection draws two
size-3 tournament winners for each GP proposal. Two parent elites plus the 46
best of 48 offspring form each new population. The training-selected champion is
best-so-far across all evaluated proposals.

## Physics and scoring

The AC solver stamps `Y_C=j*2*pi*f*C` and `Y_L=1/(j*2*pi*f*L)`, along with the fixed
source/load resistances. The ideal source voltage is a known node potential.
Ideal wires use union-find contraction. Floating component islands and singular
or nonfinite solutions are invalid. Empty disconnected output with its load and
ground-shorted output are valid zero responses. Unused allocated nodes do not
create spurious matrix singularities. Row scaling changes units of equations;
it adds no conductance. A relative residual check detects unusable numerical
solutions, without an arbitrary condition-number cutoff.

Responses are normalized by the fixed 0.5 through gain. Each band's mean squared
error receives weight 0.5. Transition frequencies are unscored. Invalid cases
receive 1e9; finite squared residuals clip at 1e6. Training and dense assessment
use their frozen grids plus exact requirement boundaries. Training evaluation
returns only scalar records and has no assessment callback. Held-out evaluation
requires a completed search and its already-selected champion.

## Execution and accounting

Every proposed program, copied child, duplicate and invalid circuit consumes one
slot. Cache hits save simulation only. Results distinguish proposal-weighted
invalid cases, actually computed invalid cases, candidate-level computations,
case evaluations including failed development, and calls to the nodal solver.
The four random timing candidates use a separate seed and discard their scores;
they are not part of the 2,304 pilot proposal slots.

The launcher starts one process with a lock inherited by the worker, enforces a
cumulative 1,200-second batch allowance, and records completed outcomes. The worker
sets a 768 MiB RLIMIT_AS and all BLAS thread variables to 1 before numerical-library
imports. It spawns no pools. Peak RSS comes from Linux `getrusage(RUSAGE_SELF)`;
per-run RSS is the process's cumulative high-water mark. Output writers include
temporary atomic files in a 100 MiB ceiling. Compact generation checkpoints retain
current population/offspring, best-so-far, RNG, proposal counters, bounded scalar
cache and candidate hashes, never full population histories or per-candidate files.

Normal repeated execution leaves a completed batch untouched. A compatible partial
run resumes from its latest checkpoint, including a reserved pending proposal.
Configuration, package versions and source hash must match. A cooperative timeout
saves partial generation state; a hard-killed worker can lose work after its last
durable generation checkpoint. A launcher crash conservatively charges elapsed
wall time; it does not renew the 20-minute allowance. Exhausted time is a truthful
partial outcome, and the command reports that no allowance remains. Changes after
observing holdout results require a new future study, not replacement of this pilot.
