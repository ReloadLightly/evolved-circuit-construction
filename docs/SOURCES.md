# Primary sources and implementation decisions

Sources checked during repository initialization. This is a short research aid, not a requirement to reread everything before coding.

M1 revisited the two author-hosted papers and official DEAP GP/operator documentation.
The implemented correspondence and all reconstruction choices are recorded in
[MECHANISM.md](MECHANISM.md); observed outcomes are in [reports/m1.md](../reports/m1.md).
ngspice was absent, so M1 used loaded analytic fixtures without an ngspice comparison.
The Codex controls below describe initialization-time source checks and the
launcher's request, not an independently observed active-session model/effort.

## Scientific mechanism

1. Koza, J. R., Yu, J., Keane, M. A., and Mydlowec, W. (2000). *Use of Conditional Developmental Operators and Free Variables in Automatically Synthesizing Generalized Circuits using Genetic Programming.* https://www.genetic-programming.com/jkpdf/eh2000parameterizedfilter.pdf
   - Sections 2–4: developmental programs, requirements as inputs, and circuit evaluation. Section 4.4 explicitly requires executing only one developmental conditional branch. Section 5 reports the historical results, not ours.
2. Koza, J. R., Bennett III, F. H., Andre, D., and Keane, M. A. *Synthesis of Topology and Sizing of Analog Electrical Circuits by Means of Genetic Programming.* Author-hosted CMAME manuscript: https://www.genetic-programming.com/jkpdf/cmame.pdf
   - Construction semantics and topology/value search. Consult the relevant operator description rather than blocking on every historical default.
3. DEAP official GP tutorial: https://deap.readthedocs.io/en/master/tutorials/advanced/gp.html
   - Typed primitive sets, tree generation and representation, bloat controls. Use a custom lazy interpreter rather than eager execution of graph-modifying branches.
4. DEAP evolutionary operations: https://deap.readthedocs.io/en/master/api/tools.html
   - Tournament selection, compatible crossover, mutation. Verify actual installed APIs and pin versions used.
5. ngspice official documentation: https://ngspice.sourceforge.io/docs.html
   - Netlists and circuit analysis reference. An optional independent simulator check, not an M1 system-install dependency.

## Explicit reconstruction decisions

The restricted passive grammar, embryo details, normalized inputs, value bounds, solver implementation, fitness, grids, success thresholds, populations, probabilities, budgets, and omission of automatically defined subroutines are ours. EXPERIMENT.md fixes them for the experiment. They are not asserted to be identical to Koza's. Closed-form circuit tests validate the nodal solver. No fabricated physical response, fixed filter-template dispatch, or LLM-designed candidate is an acceptable replacement.

## Codex and local workflow

6. Official models documentation: https://developers.openai.com/codex/models
   - Redirects to ChatGPT Learn. Documents gpt-6-astra and Ultra as maximum reasoning with automatic delegation. Ultra is not just an informal name for xhigh.
7. Official CLI reference: https://developers.openai.com/codex/cli/reference
   - Global --ask-for-approval never, --sandbox workspace-write, configuration overrides, and live search.
8. Official noninteractive execution: https://developers.openai.com/codex/noninteractive
   - codex exec, stdin prompts, --output-last-message, and --ephemeral. Explicit sandbox settings instead of deprecated --full-auto.
9. Official configuration reference: https://developers.openai.com/codex/config-reference
   - forced_login_method=chatgpt, sandbox_workspace_write.network_access, agents.enabled, agents.max_concurrent_threads_per_session. Its reasoning-effort enumeration was less complete than the current model documentation/source at inspection.
10. OpenAI Codex source, inspected revision 3052bbcf8c9d48e130599308c583784db43e57aa:
    - https://github.com/openai/codex/blob/3052bbcf8c9d48e130599308c583784db43e57aa/codex-rs/protocol/src/openai_models/reasoning_effort.rs
    - https://github.com/openai/codex/blob/3052bbcf8c9d48e130599308c583784db43e57aa/codex-rs/tui/src/app_server_session.rs
    - Native source handles ReasoningEffort::Ultra and stores it as model_reasoning_effort. Ultra's ordinary inference effort is resolved through model metadata; a lower-level inference label is not, by itself, proof Ultra was disabled. The launcher requests model_reasoning_effort="ultra" without silently substituting xhigh. Installed version/account availability still must be observed locally.
11. VS Code WSL: https://code.visualstudio.com/docs/remote/wsl
12. GitHub CLI repository metadata: https://cli.github.com/manual/gh_repo_edit

The GitHub connector used for initialization supports repository file writes but exposes no repository-description edit action. ABOUT.txt contains the requested description. The local launcher applies it with gh repo edit under the owner's existing authorization. Do not claim the About field was changed until that operation succeeds.
