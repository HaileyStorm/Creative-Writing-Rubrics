# TTCW partial-overlap development diagnostic

Two small, retrospective comparisons examined whether selected HBQ leaves
track existing TTCW expert assessments on related questions. They use the same
stories and human target for each comparison with the saved full HBQ score.
The results are exploratory and do not establish a better rubric.

| Existing cohort | TTCW question | Partial-overlap rho | Full HBQ rho |
| --- | --- | ---: | ---: |
| 29 historical reports | Ending | 0.714 | 0.596 |
| 29 historical reports | Character development | 0.232 | 0.017 |
| 28 shared-method works | Ending | 0.707 | 0.633 |
| 28 shared-method works | Character development | 0.203 | -0.009 |

These are average-tie Spearman correlations against the fraction of YES among
three existing ballots for the corresponding TTCW question. They are not
comparisons against the overall 14-question creativity target. The overlap
score is the equal-weighted YES fraction of two saved effective verdicts,
available only when both are YES or NO. The full score is the saved canonical
HBQ result, with its original eligibility, gates and coverage; it was not
recomputed. Both scores use exactly the same works and target in each row.

The ending view uses `core.length_and_scope_fit.ending` and
`form.prose.short_story.ending`. These assess the endpoint and central pressure;
they do not establish that the ending was earned. The character view uses
`craft.narrative.characterization.dimensionality` and
`craft.narrative.characterization.development`. They focus on major characters
and scope-qualified development, whereas the human question concerns every
character and appropriate complexity. The mappings are partial, not equivalent
human labels for those leaves. Twelve other TTCW questions are unmapped.

All four leaves were binary and all full scores eligible in the included
reports. Seven or eight of the original 36 works are missing, and neither
cohort meets the prospective 33-work rule. Each cohort spans twelve plot
groups; the 28-work cohort is a subset, not an independent replication. Each
overlap score has only three distinct levels. In the 29-work cohort, 28 or 29
works tie on the overlap score, depending on criterion; the character target
has only two observed levels. The aggregate file includes the tie counts.

The cohort, labels, historical outcomes and candidate leaves had already been
inspected. The mapping is a post-hoc development sensitivity analysis, not an
independent confirmation. No confidence intervals, causal explanation, winner
or promotion are claimed. The previously published HANNA overlap diagnostic is
a separate study. No model requests, new human labels or canonical rescoring
were made for this analysis.

`aggregate.json` contains the point estimates, denominators, tie and missingness
counts, limitations and source hashes. The underlying private reports, labels,
frozen membership, and analysis source are not included; the source hashes
permit checking those inputs where authorized but do not make this aggregate
independently reproducible without them.
