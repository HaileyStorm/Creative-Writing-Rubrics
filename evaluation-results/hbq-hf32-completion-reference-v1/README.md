# HF32 scorer-completion ranges and human references

This post-result development analysis examines whether the score ranges from
fixed-input completions separate works in the previously reported HF32 pilot.
It reuses existing judgments and references. It does not add judgments, validate
individual completions, establish population reliability or promote a candidate.
The [earlier HF32 report](../hbq-hf32-frozen708-human-reference-v1/README.md)
describes the study, attrition, target definitions and matched correlations.

## Inputs and calculation

The fixed pilot planned 32 works. Twenty-seven have complete scored HBQ banks;
five incomplete banks remain excluded. For each of the 27, the analysis changes
score-affecting `CANNOT_ASSESS` states through the allowed `NO`, `YES` and
`NOT_APPLICABLE` substitutions while holding the other verdicts and scoring
inputs fixed. The resulting scorer range is a mathematical sensitivity range,
not a confidence or prediction interval, and its substitutions are not new
model or human judgments.

All 27 grouped ranges matched the saved historical bounds. Seventeen also
matched full enumeration; the other ten rely on guarded grouping and direct
scorer witnesses, not full enumeration. The analysis is specific to the
retained banks and its fixed-activity, gate and dependency guards; it is not a
general proof for arbitrary banks. Across all 27 banks, 248 of 351 unordered
pairs have disjoint ranges; 103 overlap or touch.

## Matched human-reference comparison

For each reference axis, 19 works have the HBQ score, TTCW14 score and relevant
human reference. The expert reference is the mean of exactly two finite expert
creativity ratings; the reader reference is the median of available finite
nonexpert creativity ratings. These are different constructs. Each axis has
171 unordered work pairs, and the 19 works need not be identical across axes.
The previously published matched Spearman correlations are repeated here for
context, not presented as a new test.

| Reference | HBQ rho | TTCW14 rho | Disjoint-range pairs | Overlap or touch |
| --- | ---: | ---: | ---: | ---: |
| Expert mean | 0.293140 | 0.232532 | 120 | 51 |
| Reader median | 0.390412 | 0.364687 | 121 | 50 |

Within each disjoint-range stratum, a reference tie has no direction and is
counted separately. Among the remaining pairs, agreement means that a method's
observed score ordering has the same direction as the human-reference ordering.
The same pairs and reference ties are used for both methods.

| Reference | Reference ties | HBQ agree / disagree | TTCW14 agree / disagree / tied |
| --- | ---: | ---: | ---: |
| Expert mean, 120 disjoint pairs | 23 | 62 / 35 | 53 / 29 / 15 |
| Reader median, 121 disjoint pairs | 20 | 72 / 29 | 63 / 23 / 15 |

[aggregate.json](aggregate.json) also contains the overlap-or-touch strata and
full precision. Pair counts reuse works and are not independent observations.
Disjoint scorer ranges do not prove that a model judgment or a human reference
is correct, and their selection does not justify a method-superiority claim.
This is a previously opened, complete-case development subset, not a prospective
confirmation cohort. Raters and works can be dependent; missing scores and
targets can affect the comparison. No new confidence intervals, model calls,
human labels or candidate promotion follow from this analysis.

## Reproduction and privacy

`analyze.py` regenerates `aggregate.json` from two exact private retained inputs:
the HF32 analysis result (SHA-256
`e8bfc8cb83c91f4f26c4f901bc0f9fef9e993072b509c175baccafcddaad9fe7`)
and grouped-completion result (SHA-256
`469806acefd2f4cc92908f6b31e3c5f0afae3b4e8c15b9061892f89293994a0c`).
Supply their local paths with `--source` and `--manifest`; output is JSON on
standard output. The script checks both digests, source joins, case uniqueness,
score equality and range equality. The inputs include private records and are
not published, so public readers cannot independently reproduce this result
without authorized access to them. This publication contains aggregates and
opaque commitments only, with no creative text or individual ratings.
