# TTCW uncertainty-preserving ladder: no observed change

The existing `uncertainty_preserving_ladder_v1` produced identical scores on all
29 complete TTCW banks. Scores, statuses, weighted coverage and sensitivity
bounds matched the historical scorer exactly. No projection changes occurred:
this sample did not exercise the mechanism's distinguishing behavior and
provides no observed alignment improvement.

| Fixed development cohort | Historical Spearman | Candidate Spearman | Difference |
| --- | ---: | ---: | ---: |
| 29 complete HBQ banks | 0.686260 | 0.686260 | 0 |
| 28 works shared by all five benchmark methods | 0.711917 | 0.711917 | 0 |

The human reference is the existing fraction of YES ballots across fourteen
tests and three expert ballots per test. It is not a direct preference label or
42 independent experts. Historical and type/token-ratio correlations are reused
from the [source-control analysis](../hbq-sol-ttcw-source-controls-20261026/README.md)
only at identical story membership. Candidate correlations were calculated in
this run; no confidence intervals were estimated.

This is a post-result development comparison, selected after the earlier
benchmark and source-control results. Seven of the planned 36 banks remain
missing and were not synthesized as CANNOT_ASSESS. The original 33-work rule is
unmet, and the retained works share twelve plot groups. This is not unused
confirmation, general validation of the candidate, or a promotion decision.

The [opt-in implementation](../../src/hbqrs/ladder_uncertainty.py) changes
effective scoring states while preserving original judge answers, weights,
modules, prompts and context. Original complete banks undergo strict admission;
projected states are derived scoring inputs, not new judgments or independently
admitted votes. The historical task-contract setting remains unchanged. The
older MFA experiment's decision and interval rules are not transferred here.
Rubric sensitivity bounds are not statistical confidence intervals.

The 29 banks contain 5,162 original leaf answers in 667 packets. Reprocessing
made 29 ladder calls and 58 canonical score calculations, with 174 intrinsic
compilations. These are implementation operations on the same original banks,
not independent judgments or statistical replicates. There were no provider
calls, native receipt replays, new labels or changes to canonical defaults.

[analysis.json](analysis.json) contains aggregate results and source commitments.
Raw responses, individual reference labels and private provenance remain local.
