# Agent-led component recombination

This is the default discovery path for the performance track. The agent reads the paper cards and decides which mechanisms are worth combining. The user supplies constraints, not a combination direction.

## Inputs

- Hand-written paper cards and their local extracts.
- User constraints: available time, compute, datasets, and whether a local benchmark is required.
- No user-selected pair of papers is required.

## Step 1: extract components

For each candidate paper, write one row:

| field | meaning |
|---|---|
| mechanism | what the method actually does, not its name |
| input | what representation it consumes |
| output | what it produces |
| bottleneck | which failure mode it addresses |
| assumption | when it is valid |
| cost | runtime, memory, implementation burden |
| known failure | where it breaks or is untested |

A card without a mechanism row is only a lead, not a component.

## Step 2: build a compatibility matrix

Compare pairs. A pair is worth testing only when:

- the two components act at different stages
- they address different bottlenecks
- their interfaces can be connected without a new hidden model
- both have a measurable baseline
- the combined cost fits the pilot budget

Reject or defer a pair when:

- both components solve the same bottleneck
- one component subsumes the other
- the integration needs data or code that is unavailable
- the only claimed gain is "more information"
- the pair cannot be compared under the same budget
- the result would only be a definitional audit

## Step 3: propose one hybrid

The agent writes one candidate, not a list of possible directions:

- base method A and base method B
- two components and the exact integration point
- why the combination should improve a named metric
- expected gain and the smallest useful pilot
- at least two baselines, including naive concatenation and a random-component control
- a non-empty source for each component in component_sources, and at least two rejected pairs with reasons
- datasets, metrics, compute budget
- remove-one ablation
- kill condition

Use the performance brief schema and the pilot gate.

## Step 4: pilot and decide

Run the pilot on at least three local datasets and three seeds. A candidate is promising only when it beats the best baseline by the declared threshold on at least two thirds of datasets, the remove-one ablation drops, a random-component control does not beat the hybrid, and any declared coverage/runtime constraints hold. Otherwise archive it as weak or reject.

## Human role

The human sets constraints and can veto a candidate. The human does not need to supply the combination. The agent must show the source cards and the rejected pairs, so the judgment is auditable.

## Anti-patterns

- asking the user to name the two papers to combine
- combining methods because both are popular
- hiding a new hyperparameter inside the integration
- comparing against a weak baseline
- treating a definitional identity as a performance result
