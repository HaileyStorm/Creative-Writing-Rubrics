# S2 nonpoetry scope treatment: aggregate result v1

This is the aggregate-only public result for the S2 nonpoetry scope treatment
execution. It publishes no fixture text, expected labels, individual outcomes,
prompts, model outputs, private evidence, paths, or provider-session metadata.
The machine-readable result is
[s2-nonpoetry-scope-treatment-public-aggregate.v1.json](s2-nonpoetry-scope-treatment-public-aggregate.v1.json).

## Result

All 27 new singleton requests were accepted on their first attempt, with zero
retries. Six immutable accepted calls were reused under the frozen reuse plan,
so the diagnostic evaluates 33 accepted calls total. The fixed geometry has
three repetitions per cell: four baseline passage cells, four candidate passage
cells, and three corrected nonpassage controls.

The development-only decision is **DIAGNOSTIC_FAIL**. Baseline passage cells
passed 2/4; candidate passage cells passed 3/4; corrected nonpassage controls
passed 0/3. The only improvement was `missing_required_evidence`, from 2/3 in
the baseline to 3/3 in the candidate. Material failure remained 0/3 in both
the baseline and candidate arms.

No promotion follows from this result. It does not authorize a prompt, rubric,
leaf, ownership, split, or weight change.

## What this supports—and does not

This is negative development evidence, not a treatment-effect claim. The
candidate does not clear the four-passage-cell gate, and the corrected
nonpassage controls all fail. The one improved cell cannot establish a causal
benefit while material failure remains unresolved in both arms.

The sealed private settlement remains the authority for receipt-level
verification. This public package binds its aggregate findings and opaque
receipt commitments without copying the private settlement or any underlying
material.

## Local verification

From the repository root, run:

```powershell
python evaluation-results/hbq-nonpoetry-scope-treatment-v1-result-v1/verify_output.py
```

The verifier checks the fixed aggregate and README digests, arithmetic,
lineage commitments, the small file allowlist, and forbidden private-metadata
patterns.
