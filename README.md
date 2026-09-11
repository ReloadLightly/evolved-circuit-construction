# Evolved Circuit Construction

**Discovering conditional, parameterized analog-filter construction programs with genetic programming**

**Status:** Research protocol and Codex implementation handoff. No circuit-search experiment has been run in this repository yet. The next task must deliver executable code and measured pilot results, not another planning document.

## Abstract

This project investigates how genetic programming can discover executable procedures that construct different analog filters for different requirements. We reconstruct the mechanisms of Koza-style developmental circuit synthesis: a program develops an initial circuit, conditional execution changes construction, numerical expressions determine component values, and electrical simulation supplies fitness [1, 2]. The study tests evolutionary search against random search and separates the contributions of conditional construction, input-dependent sizing, and crossover. Faithfulness means preserving these mechanisms, not duplicating historical code, hardware, or every numerical setting. This is an independent reconstruction; results are pending.

## 1. Introduction

The research object is a **circuit-construction program**, not a fixed circuit or a vector of component values. A single candidate receives passband and stopband boundaries and constructs a circuit for each input pair. Our question is whether evolution discovers useful construction procedures and whether those procedures generalize to unseen requirements.

The project is exclusively about genetic programming, circuit construction, computational experiment design, and hypothesis testing. There is no ShinkaEvolve, geopolitical application, reinforcement learning, or LLM-generated-candidate experiment.

## 2. Related Work

Koza, Yu, Keane, and Mydlowec's conditional-filter study is the initiating case [1]. The broader circuit-synthesis treatment explains developmental construction and topology/sizing search [2]. DEAP provides reusable typed-GP machinery [3]. ngspice supplies an independent circuit-simulation reference where available [4].

## 3. Method

The intended pipeline is:

`typed construction tree + requirements -> development trace -> circuit netlist -> AC response -> fitness -> selection and variation`

The reconstruction will use a small passive-circuit language, lazy conditional execution, bounded numerical expressions, tournament selection, compatible subtree crossover, mutation, and elitism. Component placement and values must come from executing the genotype, not hand-written filter templates. A small NumPy nodal AC solver keeps repeated evaluations local and lightweight; analytic fixtures check the physics, and ngspice cross-checks are added when the executable is already available. Simulator choice is an explicit implementation reconstruction, not a change to the discovery problem.

The full specification, including fixed source/load normalization and prevention of test-set leakage, is in [Experimental Design](docs/EXPERIMENT.md).

## 4. Experimental Design

| Hypothesis | Controlled comparison | Primary outcome |
|---|---|---|
| H1: Fitness-guided evolution improves search | Full GP versus independent random program search | Held-out requirement loss at equal proposal budgets |
| H2: Conditional construction helps | Full GP versus GP without developmental conditionals | Held-out loss and inspected structural changes |
| H3: Input-dependent sizing helps generalization | Full GP versus constants-only component expressions, with condition inputs retained | Interpolation loss |
| H4: Crossover helps search | Full GP versus mutation-only GP | Held-out loss at equal proposal budgets |

These are falsifiable expectations, not promised outcomes. In particular, H2 does not assume that a fixed topology with varying component values cannot realize different responses.

The first task runs only a small H1 pilot: three paired seeds, two methods, 384 candidate proposal slots per method/seed. Later, a separate task may run the five-arm study using the predeclared design. Pilot findings are not confirmatory evidence.

## 5. Results

**Pending.** No evolved champion, simulator validation, runtime measurement, or hypothesis result is claimed yet. After each executed experiment this section must link to its report, commands, seed-level outcomes, and representative programs. Incomplete and negative results remain visible.

## 6. Discussion

Interpret results in terms of search, representation, and generalization. An attractive circuit diagram is not evidence of successful filtering. A passing unit test is not evidence that evolution improves fitness. A best-of-run example is not evidence of reliable performance across seeds.

## 7. Limitations

This is initially a small-budget study of ideal passive components. Its grammar, numerical bounds, training grid, and search budget restrict possible discoveries. Simulator agreement does not establish real-hardware performance. A successful learning experiment would not reproduce the historical computational scale or establish human-competitive engineering performance.

## 8. Reproducibility

The setup and next task are in [Codex M1](docs/CODEX_M1.md). Once cloned into WSL and authenticated to Codex with ChatGPT and to GitHub with `gh`, start the implementation task with:

```bash
bash scripts/run_codex.sh
```

The launcher requests **gpt-6-astra / Ultra**, uses `approval_policy=never`, enables research network access inside a workspace-write sandbox, and publishes repository changes after the agent returns. It never switches to API-key billing or a different model. The task uses one experiment worker, bounded computations, local checkpoints, and no GitHub Actions. A session or hardware failure can still interrupt work; existing artifacts are preserved rather than silently restarted.

**Current implementation status:** The launcher is present; the GP package and experiment commands will be created and actually executed by M1. Do not advertise future commands as already runnable.

## 9. Conclusion

The project aims to make evolutionary program discovery inspectable: show what the program says, how it constructs a circuit, how that circuit behaves, and whether the procedure improves through selection. Conclusions will be revised from measured evidence.

## References

1. Koza, J. R., Yu, J., Keane, M. A., and Mydlowec, W. (2000). *Use of Conditional Developmental Operators and Free Variables in Automatically Synthesizing Generalized Circuits using Genetic Programming.* [Author-hosted paper](https://www.genetic-programming.com/jkpdf/eh2000parameterizedfilter.pdf).
2. Koza, J. R., Bennett III, F. H., Andre, D., and Keane, M. A. *Synthesis of Topology and Sizing of Analog Electrical Circuits by Means of Genetic Programming.* [Author-hosted CMAME manuscript](https://www.genetic-programming.com/jkpdf/cmame.pdf).
3. [DEAP: Genetic Programming](https://deap.readthedocs.io/en/master/tutorials/advanced/gp.html).
4. [ngspice documentation](https://ngspice.sourceforge.io/docs.html).

Implementation-source notes and verified Codex controls are recorded in [Sources](docs/SOURCES.md). The repository follows the owner's scientific-paper convention; the exact-version standard pointer is [here](SCIENTIFIC_REPOSITORY_STANDARD.md). Licensing has not yet been selected; no third-party paper or original implementation is bundled.
