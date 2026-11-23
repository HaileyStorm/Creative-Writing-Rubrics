# Missingness sensitivity of long-form agreement

The saved comparison of two historical passes over one novella reported
four-state Cohen's kappa 0.8272 for 139 matched leaves; 16 of the 155 planned
pairs were missing. Allowing **both labels of each missing pair to vary freely**
gives an exact relaxed range of **0.5621 to 0.8922**. This range measures
sensitivity to missing outcomes, not uncertainty from sampling.

The relaxation is wider than the information actually retained: eight missing
pairs have an earlier admitted label and eight have a later admitted label, but
the public aggregate does not disclose those labels. The interval is an outer
bound for completions consistent with those one-sided observations, not an
assertion that its endpoints are actually attainable. It does not replace the
observed statistic or assign labels to missing cases.

The earlier and later passes used different historical runtime and transport
arrangements. Leaves share packets and one work. The result is not controlled
repeatability, human alignment, a confidence interval, a whole-work score or
proof of native provenance. No additional judgments or model calls were made.
The original [report](../hbq-sol-longform-saved-state-contrast-20261029/README.md)
retains its own raw-agreement bounds and qualification limits.

`analyze.py` reads the pinned public report from Git and checks its SHA-256.
For each of 969 possible four-state row margins and 969 column margins for the
missing pairs, it calculates the minimum and maximum feasible diagonal counts.
It compares kappa values as integer fractions; the extremal values and exact
fractions are in `aggregate.json`. Reproduce with:

```
python -B evaluation-results/hbq-longform-kappa-missingness-v1/analyze.py --repo . --verify evaluation-results/hbq-longform-kappa-missingness-v1/aggregate.json
```
