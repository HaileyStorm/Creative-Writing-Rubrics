# Sol / TTCW: interim comparison on ten shared stories

26 October 2026. **Incomplete development evidence; collection continues.** The fixed snapshot contains 438 distinct accepted saved returns and ten stories with numeric scores from all five scalar methods. Every row below uses those same ten stories, representing six of the planned twelve plot groups.

| Method | Spearman rho against the expert reference | Distinct scores on the same ten stories |
|---|---:|---:|
| Canonical HBQ | 0.705 | 10 |
| TTCW14 | 0.315 | 7 |
| Oregon | 0.195 | 3 |
| Holistic | Undefined: constant scores | 1 |
| Compact | Undefined: constant scores | 1 |

The expert reference is the existing mean of 42 binary judgments per story: fourteen tests assessed by three experts. These are repeated judgments, not 42 independent people. Spearman correlation uses average tied ranks. TTCW14 scores are fractions of fourteen passed tests on a 0–1 scale. Other native scales are HBQ 0–100, Oregon 6–36, holistic 1–7 and compact 1–5. The aggregate file retains full precision, matched score ranges, tie counts and exact floor/ceiling counts.

HBQ has the highest observed correlation in this particular shared subset. **The result does not establish a winning method or a rubric improvement.** Twenty-six of the planned 36 stories lack at least one numeric method score in this snapshot. Completion availability selects the ten-story subset; it is neither a random sample nor unused confirmation. The unchanged primary requirement is 33 shared numeric works. No confidence interval, bootstrap, significance result or population generalization is reported. A constant vector gives an undefined correlation, not zero.

Numeric availability across the entire snapshot is HBQ 10, TTCW14 22, Oregon 18, holistic 16 and compact 20. Those unequal subsets are coverage information and should not be used to rank methods. On the shared ten, neither HBQ nor the comparators reach an exact scale floor or ceiling. Absence of exact endpoints does not rule out score compression: holistic and compact each return one value on this subset, and Oregon returns three.

## Fixed snapshot and execution limits

The saved view contains 437 producer-admitted records and one separately recovered answer from the same original attempt. Recovery used already saved native events and the final answer; it sent no request. The original failed/no-resend record remains preserved. The 328 parent record objects remain unchanged. One fixed augmented view supplied all 180 story/method profile rows and the analysis. Ten complete HBQ banks passed through the frozen scoring path; analysis reused the resulting scores. The exporter only copies saved associations and computes elementary distribution counts. It does not rerun native admission, semantic validation, scoring, reference-label joins or correlations.

The requested judge is `gpt-6.1-sol` at high, with all collection-model tools disabled. Local catalog evidence and saved receipts support zero observed tool activity. Native client versions 0.163 and 0.164 occur in the retained provenance. That evidence does not establish backend, auxiliary-path, production-wire or sampler equivalence; records lacking native version fields remain unknown. Historical cached qualification limits, including the original ordinal-one join limitation, continue to apply. Independent agent review is not additional human validation.

The collection was not stopped for this snapshot. The original producer reader's stopped status is retained for the failed attempt; the current worker uses its separately reconciled continuation. This report is a fixed scientific snapshot and does not describe the later live request count. Initial coverage continues before repeat or new-form inference. No candidate is promoted, no unused confirmation reference is opened, and the full program remains incomplete.

The [20 October stopped report](../hbq-sol-ttcw-stopped-development-20261020/README.md) retains its original 328-result cohort and historical claims. This separate report adds the first published matched ten-story comparison without replacing that evidence. Current priorities remain in the [Sol execution amendment](../../docs/CWR_SOL_EXECUTION_20261020.md).

## Sources and reproduction

Story-source pin: Salesforce/ttcw_creativity_eval at `278745280a0bfebf4151bfa687add38ba2c98d61`, CSV SHA-256 `28cf816670e73c82d3580c1e59edabcf872c60328727b007068429e22f0acbcb`. Expert annotations: [Salesforce creativity_eval, Art_or_Artifice](https://github.com/salesforce/creativity_eval/tree/3d029879df6878f611363db88cc02d465699bc51/Art_or_Artifice), `annotations/ttcw_annotations.json`, Git blob `502de8d779d7fb38b8df569e64c2a6d0d4ae6e51`. Source restrictions continue to apply; underlying texts and raw labels are not redistributed here.

`analysis-profile.json` records the frozen method/source commitments and this retrospective export's limits. `source.py` creates `aggregates.json` from three exact retained private inputs:

```text
python source.py --joined SAVED_JOINED_JSON --profiles SAVED_PROFILES_JSON --analysis SAVED_ANALYSIS_JSON --output NEW_AGGREGATE_JSON
```

The private records remain necessary to reproduce the source joins and original statistics. Hashes and this aggregate exporter alone do not provide full public reproduction. Stories, raw ballots, work IDs, native identities, account details and operational logs are excluded from this package.
