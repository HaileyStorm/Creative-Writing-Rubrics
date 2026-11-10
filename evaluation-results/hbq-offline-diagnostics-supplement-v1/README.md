# Four offline diagnostics on retained CWR evidence

These retrospective supplements examine existing repeat behavior and descriptive
associations. They add no model requests, labels, prospective validation or
candidate promotion. Each retains the original study's selection, missingness and
historical runtime limitations. The main research program remains incomplete.

## TTCW repeat disagreements and exact evidence turnover

Two selected complete bank pairs each contain 178 matched questions in 23
packets. The pairs have 8 and 10 state changes: 17 distinct questions change,
and one changes in both works. All 18 changed-answer pairs have unequal exact
evidence-object sets. So do 329 of 338 stable-answer pairs; nine stable pairs
have identical sets. Of the changes, 15 are YES/NO flips and three change
applicability. No CANNOT_ASSESS transition occurs.

Evidence sets compare full canonical JSON objects, ignoring order and duplicates
without normalizing text. Edited references or summaries count as turnover.
Pervasive exact turnover among stable answers prevents using turnover alone to
explain reversals. Equality is not semantic validity, support quality or causality.
Two selected works and dependent questions cannot establish population reliability.

## Poetry scalar-induced ordering across cycles

Four frozen synthetic families each have three variants and three cycles. Three
variant pairs times three cycle contrasts give 36 planned comparisons per arm.
Every observed comparison requires four eligible scalar scores. Comparator-only
families are excluded. These are scalar-induced orders, separate from the
original directly judged pairwise preferences.

| Arm | Observed / planned | Stable strict | Stable tie | Strict reversal | Tie entry / exit |
| --- | ---: | ---: | ---: | ---: | ---: |
| HBQ | 20 / 36 | 15 | 3 | 2 | 0 / 0 |
| Holistic | 36 / 36 | 21 | 12 | 1 | 1 / 1 |
| Compact | 36 / 36 | 18 | 18 | 0 | 0 / 0 |
| POEMetric | 24 / 36 | 5 | 17 | 0 | 0 / 2 |

Score differences sometimes change relative ordering. Unequal availability and
substantial tied-score compression prevent an arm-winner claim. Families,
artifacts and cycle contrasts are dependent; creator roles supply no quality
oracle. These counts establish neither correctness nor current-runtime reliability.
The complete aggregate retains form-by-cycle and missingness summaries.

## TTCW single-control partial rank associations

Using saved rounded coefficients, the partial correlation is
`(rXY-rXZ*rYZ)/sqrt((1-rXZ²)*(1-rYZ²))`, where X is HBQ rank, Y expert-mean rank
and Z one control's rank. This is linear rank-residual correlation; residuals are
not reranked. The controls are evaluated separately.

| Cohort | Unadjusted rho | Token-count control | Raw-TTR control |
| --- | ---: | ---: | ---: |
| Primary shared28 | 0.711917 | 0.539836 | 0.580712 |
| Dependent HBQ29 | 0.686260 | 0.539468 | 0.564900 |

Both cohorts represent 12 plot groups; eight/seven original works are missing.
The original shared33 rule remains unmet. Decimal arithmetic cannot recover
precision lost in the source coefficients. Associations remaining positive after
one adjustment do not establish a distinctive quality signal or human validity.
This is post-hoc, with no joint controls, causal interpretation, inference,
confidence intervals or adjusted competitor comparison. HBQ29 is not independent
replication. Raw TTR is itself length-dependent.

## Dryad DEV30 single-story influence

The pinned previously opened 30-story development cohort reproduces its original
two associations. Each of 30 single-story omissions is reranked on 29 stories.

| Axis | Baseline rho | Delete-one range | Maximum absolute shift |
| --- | ---: | ---: | ---: |
| well_written | 0.341941 | 0.275820–0.455756 | 0.113814 |
| enjoyed | 0.377254 | 0.314934–0.475604 | 0.098350 |

All 30 values per axis remain positive and defined. The cohort was selected after
partial model observation. Shared raters, topics and conditions remain; individual
deletions do not address clustered dependence. These are local sensitivity
descriptions, not significance tests, population intervals or generalization.
The DEV30 cohort differs from other matched common27 Dryad comparisons.

## Regeneration and access requirements

`project.py` regenerates `report.json` from the four exact reviewed aggregates
included here. This is an aggregate projection, not a fresh computation from
stories, responses or reference labels. It verifies their hashes and rechecks
their bytes. Use standard-library Python with an unused output path:

```
python -I -B project.py --output <new-output-file.json>
```

Optional `recompute/` adapters preserve the original scientific function bodies
and add explicit input paths, hash checks and create-only output receipts.
`input_contracts.json` specifies required input hashes, access and commands.
TTCW repeat, poetry and Dryad recomputation require retained private inputs that
are not distributed here. Their raw-data reproducibility is conditional on
authorized access to those exact bytes. The partial-rank adapter uses the existing
public source-control report. Dryad additionally imports the exact pinned public
analysis module, whose file is required; it does not contact a provider.

The adapters retain syntax checks and AST comparisons to their reviewed sources.
All four were then executed once from this package location with the exact pinned
inputs; regenerated aggregate objects matched the independently reviewed originals.
The distributed summary projection also reproduced byte for byte.
`runtime_acceptance.json` records that Windows/Python 3.12 acceptance and input
commitments. Same-input regeneration is engineering acceptance, not independent
scientific replication or new provider/account/sampler qualification.
`source_mapping.json` binds the original and adapted code and aggregate hashes.

For relocation, preserve the package's internal layout. Supply actual input
locations through command-line arguments; no local account, checkout, hidden
runtime or private path is assumed. A changed input requires a new analysis
identity and review rather than changing a pin in place. `FILELIST.json` lists
every distributed file except itself with byte counts and hashes. No individual
story/question identifiers, raw text, response metadata or individual labels are
included.
