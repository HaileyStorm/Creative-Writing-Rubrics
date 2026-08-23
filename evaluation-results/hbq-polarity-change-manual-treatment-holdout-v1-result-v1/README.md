# P1 polarity manual-treatment holdout: aggregate result v1

This is the aggregate-only public result for the sealed same-fixture P1
current-versus-treatment holdout. It publishes no fixture text, fixture
aliases, expected labels, individual outcomes, prompts, model outputs, private
evidence, paths, or provider/session/request metadata. The machine-readable
result is
[p1-manual-treatment-holdout-public-aggregate.v1.json](p1-manual-treatment-holdout-public-aggregate.v1.json).

## Result

All 120 of 120 singleton slots completed and were accepted on their first
attempt, with zero retries. The fixed geometry was twenty synthetic artifacts:
sixteen target artifacts and four controls, evaluated in two arms with three
repetitions per cell.

The predeclared decision is **NO_EFFECT**: no treatment benefit is demonstrated
under this frozen aggregate gate. Current and treatment controls each passed
12/12. Both arms passed 15/16 target cells. Their raw target matches were
47/48 for current and 46/48 for treatment. There were zero target
improvements, and no stable defect was found in both families.

NO_EFFECT means no qualifying cell benefit met the frozen gate. It does not
establish identical per-fixture outcomes or equal general performance. The
private cell mapping and all expected labels remain sealed.

## What this supports—and does not

The exact candidate appendix has been exhausted for this holdout: no qualifying
cell benefit was demonstrated. The figurative gate remains closed. No promotion
follows from this result, and it does not authorize a prompt, rubric, leaf,
ownership, split, or weight change.

The sealed private settlement remains the receipt-level verification authority.
This public package binds the retained source aggregate, settlement, and
execution inputs through opaque SHA-256 commitments without copying private
material.

## Local verification

From the repository root, run:

```powershell
python evaluation-results/hbq-polarity-change-manual-treatment-holdout-v1-result-v1/verify_output.py
```

The verifier checks the fixed aggregate and README digests, arithmetic, source
commitments, gate semantics, the three-file allowlist, and forbidden private or
overclaim patterns.
