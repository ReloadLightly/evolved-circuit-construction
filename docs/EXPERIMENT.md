# Experimental design: conditional circuit construction

**Status:** Pre-execution protocol. Numerical settings below are our reconstruction choices, not claims about Koza's historical settings. M1 implements the mechanism and the small H1 pilot. The larger study is planned, not automatically authorized by launching M1.

## 1. Question and unit of analysis

Can tree-based genetic programming discover one interpretable procedure that constructs useful lowpass and highpass filters across different input requirements? What do selection, developmental conditionals, free-variable sizing, and crossover contribute?

The genotype is a construction program. The phenotype is the circuit obtained by executing that program for a particular requirement pair. The replicate for statistical comparisons is an independent search seed, not a circuit, frequency point, or generation.

The initiating conditional-program mechanism is described in [1]; developmental circuit synthesis is described in [2]. Sources are listed in SOURCES.md. Everything more specific below is the reconstruction protocol.

## 2. Circuit task and physical evaluation

A requirement is (F1, F2), in Hz, with F1 != F2. When F1 < F2, require lowpass behavior: pass f <= F1 and suppress f >= F2. When F2 < F1, require highpass behavior: suppress f <= F2 and pass f >= F1. The interval between boundaries is not scored.

Use a 1 V AC source, fixed 1000-ohm source resistance, fixed 1000-ohm load resistance, a fixed output probe, and initially two serial modifiable wire segments. Evolve only the intervening passive L/C network. Never let a candidate modify source, load, probe, frequencies, or scoring rules.

Use a compact NumPy complex nodal AC solver: capacitor admittance j*2*pi*f*C and inductor admittance 1/(j*2*pi*f*L). Handle ideal wires by merging nodes, not a made-up gain rule. Include the fixed source/load correctly. Reject genuinely undefined/singular circuits consistently. Do not silently add conductances that change the circuit. Cross-check analytic fixtures; compare with ngspice when already available. Absence of ngspice is not a blocker and does not authorize a system install or a long simulator build.

Define amplitude A(f) = abs(Vout(f)/Vsource(f)) / 0.5. The 0.5 is the FIXED through-connection gain for the specified source/load fixture. Never normalize by each candidate's own maximum or DC response: that would reward attenuators and break highpass comparisons.

Per-case loss = 0.5*mean_pass(min((A-1)^2, 1e6)) + 0.5*mean_stop(min(A^2, 1e6)). Mean across cases gives training fitness; smaller is better. Bands and filter modes have equal weight. Invalid/nonfinite cases receive loss 1e9. Report invalid-case rate and any clipping separately. Tie-break equal fitness by fewer active components, then fewer tree nodes. Do not add an arbitrary complexity penalty to the primary loss.

The initial learning-level engineering success criterion is abs(A-1) <= 0.10 at every scored passband frequency AND A <= 0.10 at every scored stopband frequency. This is not the historical 60 dB criterion. Report continuous loss even when no circuit succeeds; never weaken the criterion after seeing test results.

## 3. Representation and search

Use DEAP for typed tree generation and compatible genetic operations, with a custom interpreter for side-effecting circuit development. Do not use eager Python evaluation to execute both branches of a construction conditional.

Provide elementary L/C creation, serial division, parallel division, connections to ground, termination/unchanged wire, and conditional development. Each operator's behavior on the current edge or construction site must be written down and tested. A simplified grounded series/parallel graph grammar is acceptable; disclose its restricted search space. Do not provide lowpass/highpass/Bessel/Butterworth/Chebyshev construction macros or seed the population with filter solutions.

Provide signed protected arithmetic and perturbable constants. Inputs may be log10(F1/1000 Hz) and log10(F2/1000 Hz); label this normalization. Component values are bounded positive transformations of evolved expressions, with L in [1e-8, 10] H and C in [1e-12, 1e-4] F. Do not hard-code inverse-frequency scaling or dispatch to filter templates outside the genotype. Keep predicate and component-value expression contexts distinguishable so the H3 ablation cannot leak frequency inputs through crossover.

Use random typed initialization, tournament size 3, compatible subtree crossover, subtree/constant mutation, and elitism. Per proposed child: crossover probability 0.70, mutation 0.25 (subtree and constant perturbation with equal probability), reproduction 0.05. Produce a population-sized offspring batch; retain two parent elites and the best remaining offspring to refill the population. Bound attempts to obtain a legal variation: after two failed attempts, retain an unchanged parent and count that proposal slot. Enforce tree/circuit limits during generation and development. No LLM calls or gradient tuning within search.

Every attempted candidate proposal consumes one slot, including duplicates, invalid circuits, and copied offspring. Pure elite carryover is not a proposal. Caching saves work, not budget. Report proposal slots, unique candidates, actual circuit evaluations, and elapsed time separately. Random search uses the identical initialization grammar and prior with no parent selection; compare equal proposal budgets, not equal generations. Cache at most 4096 scalar fitness records, not dense response histories.

## 4. Train/test separation

Training requirements: for b in {1000, 10000, 100000}, use both (b, 2*b) and (2*b, b): six cases. Training sweep: 81 log-spaced frequencies from 100 Hz to 1e6 Hz, augmented with each case's exact boundaries and deduplicated.

Held-out interpolation requirements: b = 1000*10**q for q in {0.25, 0.50, 0.75, 1.25, 1.50, 1.75}, both orientations: twelve cases. Diagnostic extrapolation: b = 1000*10**q for q in {-0.50, 2.50}, both orientations: four cases. Use 401 log-spaced frequencies over the same sweep range, plus exact boundaries, for final assessment. Also assess training requirements on this dense grid to separate frequency-grid exploitation from requirement generalization.

Select one champion per method/seed solely on training loss, with the fixed tie-break. Evaluate held-out cases only after that search has ended. Do not inspect test scores while evolving, tune using them, select champions by them, or retry bad seeds. A later substantive method change after inspecting this pilot makes the current holdout developmental evidence; a confirmatory task must then use a fresh frozen assessment set.

## 5. Hypotheses and comparisons

| ID | Falsifiable expectation | Comparison |
|---|---|---|
| H1 | Selection and variation lower held-out loss relative to random sampling | Full GP versus random program search |
| H2 | Conditional construction lowers held-out loss | Full GP versus developmental-conditional-free GP; numerical inputs remain available |
| H3 | Free-variable sizing improves interpolation | Full GP versus constants-only sizing; predicates retain F1/F2 |
| H4 | Crossover improves search under the given budget | Full GP versus mutation-only; replace crossover probability with subtree mutation |

These are total effects of the specified method changes, not universal claims. In H2, a fixed labeled topology with varying numerical values may still implement different responses; do not assume a win for conditionals by definition. Verify structural differences independently using graphs with fixed input/output/ground labels and component types, ignoring numerical values and arbitrary node names. Active construction traces should show where any difference originates. Do not reward mere branch execution or graph difference in fitness.

## 6. Budgets and sequence

**M1 pilot:** full GP and random search; seeds 101, 202, 303; population 48; 384 proposal slots per method/seed, including the initial 48 (then seven 48-offspring batches). Total 2304 slots. Pair methods by seed, use a fixed randomized within-pair execution order, and checkpoint each completed generation/run. First time and measure a very small unscored timing sample; it is not hypothesis evidence and must not tune the method. The entire experimental batch, including timing, has a 20-minute ceiling. Complete all pairs within it if feasible; otherwise publish partial counts and preserve continuation state. Do not expand the budget or replace it with a single cherry-picked example.

**Subsequent five-arm study, not part of M1:** seeds 1001 through 1020, population 96, 3072 slots per method/seed (initial population plus 31 offspring batches). This is a proposed ceiling of 307200 slots across five methods, not a claim it fits the laptop or a permission to start it now. Use pilot runtime to design bounded resumable batches before this task is launched. Freeze any revised feasible budget before observing that study's assessment results; never silently shrink just one arm.

Primary estimand: paired difference in held-out interpolation loss, full GP minus comparator. Negative favors full GP. For M1 show all three seed pairs and descriptive effects only. For the later study report a paired effect estimate and seed-level bootstrap interval, raw seed results, and all four contrasts. Intervals are descriptive/marginal unless multiplicity is explicitly handled; do not present unadjusted multiple tests as one confirmatory success. Report mode-specific losses, engineering success rates, size, and dense-grid generalization as secondary outcomes. Distinguish an implemented mechanism, a successful pilot execution, improved loss, and successful filtering.

## 7. Evidence and focused correctness checks

Validate voltage division and at least one simple lowpass and highpass against closed-form complex responses, including loaded fixtures. Manually constructed fixtures only test physics and language expressivity; never count them as evolved discoveries. Check lazy branches, deterministic development, finite bounded components, protected arithmetic, preserved fixture connections, valid typed variation, no input leakage in ablations when implemented, identical budget counting, and held-out exclusion from selection.

Save small machine-readable per-seed results, selected genotypes, per-generation best training loss, champion construction traces, netlists, representative AC plots, and actual commands/configuration/versions. Plot data must come from those artifacts. Record incomplete runs rather than discarding them. Repeated execution must resume compatible artifacts or leave completed runs unchanged. Record relevant code revision/configuration with each run; no separate provenance framework.

## 8. Completion is not a predetermined result

M1 is complete when the mechanism is implemented, its relevant tests run, the authorized comparison is executed or truthfully bounded, and the paper/report contain the actual evidence. H1 need not be supported for the task to be completed. No successful circuit, significant effect, or historically competitive result is promised in advance.
