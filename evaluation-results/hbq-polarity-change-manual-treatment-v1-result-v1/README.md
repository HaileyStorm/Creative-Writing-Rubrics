# P1 polarity manual treatment: aggregate result v1

This is the aggregate-only public result for the staged P1 manual prompt
treatment. It publishes no fixture text, expected labels, individual outcomes,
prompts, model outputs, private evidence, or provider-session metadata. The
machine-readable result is
[p1-manual-treatment-public-aggregate.v1.json](p1-manual-treatment-public-aggregate.v1.json).

## Result

All 57 of 57 singleton slots completed and were accepted on their first
attempt, with zero retries. The fixed geometry was nineteen synthetic
artifacts, eleven selected leaves, four canonical states, and three repetitions
per treatment cell.

The development-only decision is **MANUAL_TREATMENT_PASS**: all 19 of 19
scored cells passed 3/3. State-level accuracy was NO 12/12, YES 12/12,
NOT_APPLICABLE 33/33, and CANNOT_ASSESS 0/0 because this treatment screen did
not include a CANNOT_ASSESS target. The exact per-leaf aggregate state counts
are published in the JSON projection.

No promotion follows from this result. It does not authorize a prompt, rubric,
leaf, ownership, split, or weight change.

## What this supports—and does not

The manual treatment combined four matched fixture repairs with an explicit
applicability and evidence-sufficiency appendix. The aggregate is encouraging
development evidence, but it does not isolate the causal contribution of the
repairs, the appendix, or their interaction. It is not a general claim about
polarity evaluation.

The sealed same-fixture current-versus-treatment A/B holdout is the next
decision gate. Only a holdout pass, deterministic validation, and independent
Sol-high review can support a later promotion decision. This result itself
changes no public prompt or rubric content.

The sealed private settlement remains the authority for receipt-level
verification. This public package binds its aggregate and opaque receipt
commitments without copying the private settlement or any underlying material.

## Local verification

From the repository root, run:

```powershell
python evaluation-results/hbq-polarity-change-manual-treatment-v1-result-v1/verify_output.py
```

The verifier checks the fixed aggregate and README digests, arithmetic, leaf
and state allowlists, lineage commitments, the small file allowlist, and
forbidden private-metadata patterns.
