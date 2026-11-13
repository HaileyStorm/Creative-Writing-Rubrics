# Four-threshold ladder sensitivity check

This provider-free, post-result synthetic check examines the opt-in
`uncertainty_preserving_ladder_v1` policy using the two fixed short-story verdict
banks in the [scorer influence aggregate](../hbq-scorer-verdict-influence-v1/aggregate.json).
It changes only the four holistic ladder verdicts. For each bank it enumerates
all 256 combinations of YES, NO, CANNOT_ASSESS and NOT_APPLICABLE, then resolves
each CANNOT_ASSESS to YES or NO while leaving all other verdicts, including
NOT_APPLICABLE, fixed. The 625 configuration-and-completion cases per bank are
mechanical evaluations, not independent observations or 625 distinct completed
verdict vectors: multiple starting configurations resolve to the same input.
There are 81 distinct raw configurations after those resolutions. A fixed raw
NOT_APPLICABLE threshold can still cause the candidate policy to project a
higher YES to an effective CANNOT_ASSESS state, so a raw resolution need not
produce a fully assessed effective-score report.

All resolved candidate scores fell within the candidate bounds in these cases.
This is not a general guarantee, evidence of human alignment, or a basis for
promoting the candidate. It does not test other unknown leaves, other bundles,
changes to NOT_APPLICABLE, model behavior, or literary quality. Historical scoring
and its default behavior are unchanged.

With the package available locally, run:

```text
python evaluation-results/hbq-ladder-four-threshold-envelope-v1/analyze.py
```

The command prints JSON. The saved [result](result.json) records the exact public input
and source hashes observed by the analysis. Source hashes were read after the
calculation and do not independently attest the executed bytes. Changed inputs
or code require a separately identified analysis rather than silently replacing
this historical result.
