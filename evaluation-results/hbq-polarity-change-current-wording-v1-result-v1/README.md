# P1 polarity current-wording: aggregate result v1

This is the aggregate-only public result for the staged P1 polarity and
current-wording diagnostic. It publishes no fixture text, expected labels,
individual outcomes, prompts, model outputs, private evidence, or provider
session metadata. The machine-readable result is
[p1-public-aggregate.v1.json](p1-public-aggregate.v1.json).

## Result

All 132 of 132 singleton slots completed and were accepted on their first
attempt. The fixed geometry was eleven selected leaves, four canonical states,
44 synthetic artifacts, and three repetitions per cell.

The public decision is **DIAGNOSTIC_FAIL**: 29 of 33 scored cells passed, and
6 of 11 completed-but-unscored NOT_APPLICABLE controls matched. State-level
accuracy was CANNOT_ASSESS 33/33, NO 31/33, NOT_APPLICABLE 22/33, and YES
24/33. The exact per-leaf aggregate state counts are published in the JSON
projection.

No promotion follows from this result. It does not authorize a prompt, rubric,
leaf, ownership, split, or weight change.

## What this leaves unresolved

The diagnostic does not distinguish missing NOT_APPLICABLE-versus-CANNOT_ASSESS
guidance from a missing symmetric-evidence rule. It also retains oral-fixture
ambiguity and three positive carrier-evidence confounds. One duplicated run
label arose from second-resolution runner generation; it is non-invalidating
and no identifier or private record is published. These are repair-design
leads, not proof of a repair or a general claim about polarity evaluation.

The sealed private settlement remains the authority for receipt-level
verification. This public package binds its aggregate and opaque receipt
commitments without copying the private settlement or any underlying material.

## Local verification

From the repository root, run:

```powershell
python evaluation-results/hbq-polarity-change-current-wording-v1-result-v1/verify_output.py
```

The verifier checks the fixed aggregate digest, arithmetic, leaf and state
allowlists, lineage commitments, the small file allowlist, and forbidden
private-metadata patterns.
