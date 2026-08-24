# L2 text-only line-break holdout public result v1

This is the aggregate-only public projection of the settled
`hbq-l2-line-breaks-text-holdout-v1-execution-v1` execution. It does not copy
the external execution root, fixtures, prompts, expected ledger, responses,
evidence, or per-slot results.

All 24 planned text-only singleton calls completed. Six of eight cells reached
3/3; the candidate and control groups each had three perfect cells and one
miss. The frozen gate requires all eight cells to reach 3/3, so the decision is
`NO_GO` and promotion remains `none`.

The result is a narrow diagnostic, not abandonment: the text-only gate found a
stable false-positive around arbitrary dangling-article breaks and one control
variance. It supports retaining the current wording while the next repair is
designed; it does not justify a wording, ownership, split, merge, or weight
change. `public-result.json` contains aggregate counts and commitments to the
settled execution records, without their locations or contents.
