# Sol / TTCW: completed initial development collection

26 October 2026 (Denver). The initial collection is complete, with **1,035 distinct accepted saved results**. HBQ has numeric full-bank scores for 29 of 36 planned stories; TTCW14 has 35; holistic, compact and Oregon have 36 each. All five methods have scores for the same **28 stories, covering all 12 plot groups**. This is development evidence from an already opened expert reference. The original 33-shared-story requirement remains unmet; no method winner, intervention gain or candidate promotion is established.

## Matched associations

The reference is the existing mean of 14 binary creativity tests, each assessed by three experts per story. Forty-two ballots per story are not 42 independent people. Every row below compares HBQ and its comparator on that row's identical works; rows have different denominators.

| Comparator | Shared stories | HBQ Spearman rho | Comparator Spearman rho | Difference |
|---|---:|---:|---:|---:|
| TTCW14 | 28 | 0.712 | 0.423 | 0.289 |
| Holistic | 29 | 0.686 | 0.181 | 0.505 |
| Compact | 29 | 0.686 | undefined | undefined |
| Oregon | 29 | 0.686 | 0.137 | 0.550 |

All four comparisons exceed the frozen 10% missingness allowance. No HBQ comparison confidence interval is estimated. The differences are descriptive; missing stories and within-plot dependence prevent a superiority claim. Compact's correlation is undefined because its overall score is constant, rather than zero.

## Compression on the same 28 stories

| Method | Native scale | Observed range | Distinct scores | Tied unordered pairs |
|---|---:|---:|---:|---:|
| HBQ | 0–100 | 33.6722–56.6891 | 28 | 0 |
| TTCW14 | 0–1 | 0.142857–0.571429 | 7 | 60 |
| Holistic | 1–7 | 2–3 | 2 | 351 |
| Compact | 1–5 | 2 | 1 | 378 |
| Oregon | 6–36 | 19–22 | 4 | 111 |

None is at its exact scale floor or ceiling. The coarse comparators show compression within their scales; this is not literal floor saturation. Across all available stories, compact remains constant at 2 on all 36, holistic uses 2–3 on 36, and Oregon spans 18–24 on 36. Score resolution alone does not prove human alignment or validity.

The larger available sets yield marginal correlations of HBQ 0.686 (29), TTCW14 0.454 (35), holistic 0.291 (36), compact undefined (36), and Oregon 0.203 (36). Their different memberships do not support ranking those values. The exact distributions, intersections' sizes, and frozen per-statistic uncertainty outputs are in aggregates.json.

## Pair judgments and test agreement

All 72 initial ordered pair judgments are available: 61/72 (84.7%) match the direction derived from the existing expert mean scores. This reference is **not direct human preference voting**. Order averaging gives 30.5/36 (84.7%), with three consensus ties and a plot-bootstrap 95% interval of 72.2–94.4%. Three of 36 pairs reverse direction when presentation order reverses. The twelve disconnected three-story graphs do not establish a global ranking. Same-order repeats are still uncollected (0/24); reverse-order consistency does not establish repeatability.

TTCW14 matches expert-majority test decisions on 325/490 assessed cells (66.3%; 14/504 planned cells missing), and individual ballots on 949/1,470 (64.6%; 42/1,512 missing). These repeated tests and ballots are clustered observations. Per-test values, missing-outcome bounds and plot-bootstrap outputs are retained in aggregates.json.

The frozen analysis executed 17 bootstrap calls under **per-statistic** coverage rules. This does not mean 17 usable intervals: compact's constant vector makes some bootstrap statistics undefined. Undefined draws are retained without redraw; holistic's marginal interval has 19 undefined draws out of 2,000. Qualified comparator/pair/cell intervals do not supply a confidence interval for the incomplete HBQ comparisons or the all-five subset. Missing-outcome bounds are not confidence intervals. No unused confirmation was opened.

## Collection and observed resources

The fixed view contains 1,034 producer admissions and one separately verified saved response recovered from its original stopped attempt, without a resend or extra vote. All 711 continuation positions have dispositions, with no unresolved or unattempted remainder. Four continuation semantic rejects and five older nonadmitted requests remain missing and retained with no resend. They leave seven incomplete HBQ banks and one missing TTCW14 result. The final resumed worker exited successfully after 597 admissions and four semantic rejections; those worker counts cover its resumed suffix, not the full campaign. No automatic retry or unknown-reservation release occurred. Local completion does not establish account-wide remote or billing quiescence.

The judge was requested as gpt-6.1-sol/high through the designated secondary account, with all collection-model tools disabled. Captured accepted continuation receipts show zero tool activity. Retained clients include native versions 0.163 and 0.164; missing version fields remain unknown. This does not attest backend, auxiliary path, full wire, sampler or historical-account equivalence.

For accepted requests with observed native counters, total input is 11,801,799 tokens and output 2,181,227 (1,033/1,035 requests observed). Cached input 585,344 and reasoning output 639,076 are subsets, not additional tokens. Native task duration is observed for 1,034 requests: median 51.2 seconds and 90th percentile 75.9 seconds. These are host metadata, not isolated inference latency or future throughput. Failures, ambiguous requests and local resource waits are excluded. HBQ's 820 accepted packets include valid partial banks as well as the 29 complete banks; per-request figures are not per-story efficiency comparisons. No price or billing estimate is inferred. Full observed/missing counts and arm summaries are included.

## Reproduction and scope

The aggregate exporter copies saved statistics and computes only score counts, ranges, ties, endpoints and cohort metadata. It performs no live-journal join, native/semantic replay, canonical scoring, correlation/bootstrap rerun, reference-label read or provider call. All 979 serialized admitted records from the preceding fixed snapshot remain unchanged in the final view; all 1,035 accepted identities are unique. Source/version, exact input hashes and the frozen scoring commitments are recorded in analysis-profile.json and source.py. The exporter/profile were prepared after inspecting results and are not a new preregistration.

    python source.py --joined FIXED_JOINED --profiles FIXED_PROFILES --analysis FIXED_ANALYSIS --condition FROZEN_CONDITION --operations FIXED_OPERATIONS --output NEW_AGGREGATE_JSON

Raw texts, responses, ballots, story/native identities, account details and the private worklog are excluded. The earlier [15-story snapshot](../hbq-sol-ttcw-shared15-development-20261026/README.md) remains historical; changes across cohorts are not intervention effects. Canonical HBQ and frozen prompts/scoring remain unchanged. Selected repeats and the broader alignment, cross-form, candidate and release work remain open.
