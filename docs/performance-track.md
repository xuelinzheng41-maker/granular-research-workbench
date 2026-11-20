# Performance track (primary mode)

This is the primary research direction: combine complementary mechanisms into a new algorithm or optimization and test whether it beats strong baselines under a fixed budget. The audit track remains available for definition/theorem checks, but it is not the main line.

## When to use it

Use performance mode when the candidate claims that a new algorithm or a component recombination improves a metric under a fixed budget. Do not use it for theorem/definition audits; those remain audit mode.

## Required brief fields

Set top-level mode to performance. Every candidate needs a performance object with:

- base_methods: at least two methods being combined or compared
- components: at least two mechanisms, not just module names
- integration: where and how the components interact
- expected_gain: a numeric target, not "better"
- baselines: at least two, including the stronger base and a naive concatenation
- datasets: at least two, with a fixed split and seed policy
- metrics: primary and secondary metrics
- ablation: at least one remove-one or random-component control
- compute_budget_minutes: full pilot budget
- kill_if: the condition that ends the candidate

The JSON example is examples/performance-brief.json in the skill directory. shortlist.py validates these fields when mode is performance; it does not certify that the gain is real.

## Candidate pattern

Use two complementary components first, not a five-way stack:

    base method A + one mechanism from B
    -> integration point
    -> expected gain over A and B
    -> naive concatenation and remove-one ablations

Components must address different bottlenecks. "Both improve accuracy" is not a reason to combine them.

## Pilot gate

Before any full benchmark:

- 3 local datasets x 3 seeds, same split and budget
- at least two baselines plus naive concatenation
- report mean, spread, coverage/runtime, and per-dataset direction
- pass only if at least 2/3 datasets beat both bases by the declared effect (default 1.0% macro-F1), or the declared paired test excludes zero
- remove-one ablation must show each component contributes
- otherwise mark weak/reject and stop

Pilot results are local-substitute evidence. They do not reproduce a paper table and do not establish SOTA.

Run the gate on a pilot record:

    python skills/research-idea/scripts/performance_gate.py <pilot.json>

Exit 0 means promising, exit 3 means weak/reject, exit 2 means malformed input. The gate checks mean gain over the best baseline, a naive-concatenation baseline, the declared threshold, and an ablation drop. It is a filter, not a full benchmark.

## Cloud handoff

Cloud workers may read cards and propose one hybrid, but the host Python runner executes the pilot. A cloud pilot is a filter, not a paper result. Only a passed pilot goes to the local full experiment.

## Anti-patterns

- stacking modules without an integration hypothesis
- comparing against a weak baseline or a different budget
- selecting the best dataset after seeing results
- claiming accuracy gain by lowering coverage
- treating a definitional identity as a performance result
- calling a naive concatenation a new algorithm

## Evidence levels

Label every number as definitional, local-substitute, paper-worked-example, or needs_data. Performance claims require local-substitute or stronger evidence plus a baseline and an ablation.
