# Selected short-story repeatability: chance-adjusted agreement

This supplements the [pooled saved-state report](README.md) with unweighted
Cohen kappa for each cycle pairing. The data cover three selected short stories
and 178 HBQ leaves per story. First-cycle results for 24 leaves are held and
remain excluded from comparisons involving that cycle; the later cycles are
complete. Each row pools leaves across the three stories.

| Cycles | Four-state agreements / observed pairs | Four-state kappa | Pairs excluding `CANNOT_ASSESS` | Kappa excluding `CANNOT_ASSESS` |
| --- | ---: | ---: | ---: | ---: |
| 0 and 1 | 485 / 510 | 0.9160 | 508 | 0.9152 |
| 0 and 2 | 484 / 510 | 0.9126 | 508 | 0.9118 |
| 1 and 2 | 511 / 534 | 0.9264 | 532 | 0.9257 |
| All three pairings pooled | 1,480 / 1,554 | 0.9185 | 1,548 | 0.9177 |

Kappa uses the observed marginal state frequencies for its chance-agreement
term. The first calculation treats YES, NO, NOT_APPLICABLE and CANNOT_ASSESS
as four categories. The sensitivity calculation excludes any pair with a
CANNOT_ASSESS state; it retains NOT_APPLICABLE, uses a different denominator,
and is not an estimate of outcomes for the held leaves. Here all six removed
pooled pairs were CANNOT_ASSESS in both cycles, so the comparison is not
evidence that abstention was resolved.

Cycle pairs reuse the same responses, and leaves share stories; the pooled
rows are not independent observations. Kappa depends on state prevalence and
can conceal differences in the types of disagreement. These are descriptive
results on a selected development cohort, not a population reliability
interval, evidence of correctness or human alignment, or a model-comparison
claim. The held requests remain unchanged. See the original report for the
separately calculated full-plan missing-state bounds and source limitations.

`aggregate-kappa.json` contains pooled counts and exact rational kappa values.
`reproduce-kappa.py --input <private-projection>` recalculates them from the
digest-pinned private derived matrices, checks the exclusion and pooling
arithmetic, and emits no individual identifiers. It does not reconstruct the
original raw-to-derived analysis; private texts, responses and identifiers
remain local.
