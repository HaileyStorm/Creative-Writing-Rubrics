# S2 non-poetry scope sentinel: aggregate result v1

This is the aggregate-only public result for the first staged S2 non-poetry
scope diagnostic. It publishes no fixture text, expected labels, prompts,
responses, per-slot outcomes, private evidence, or provider-session metadata.
The machine-readable result is
[s2-public-aggregate.v1.json](s2-public-aggregate.v1.json).

## Result

All 60 of 60 singleton slots completed and were accepted on their first
attempt. The fixed study geometry was five selected leaves, four canonical
states, 20 synthetic artifacts, and three repetitions per cell.

The public decision is **DIAGNOSTIC_FAIL**: 10 of 15 scored cells passed, while
all 5 of 5 completed-but-unscored NOT_APPLICABLE controls matched. The exact
aggregate state counts are published per leaf in the JSON projection.

No promotion follows from this result. It does not authorize a prompt, rubric,
leaf, ownership, split, or weight change.

## What the diagnostic makes plausible

The result suggests one possible wording or polarity lead for
`scope.passage.status` and four additional fixture/oracle-isolation or
activation-boundary leads; causal diagnosis remains unresolved. These are leads
for a smallest-possible repair design, not proof of a repair or a general claim
about non-poetry evaluation. The aggregate deliberately does not identify
fixtures, cells, slot outcomes, or their expected states.

The sealed private settlement remains the authority for receipt-level
verification. This public package binds its aggregate and opaque private
receipt commitments without copying the private settlement or any underlying
material.

## Local verification

From the repository root, run:

```powershell
python evaluation-results/hbq-nonpoetry-scope-sentinel-v1-result-v1/verify_output.py
```

The verifier checks the fixed aggregate digest, result arithmetic, leaf and
state allowlists, public lineage commitments, the small file allowlist, and
forbidden private-metadata patterns.
