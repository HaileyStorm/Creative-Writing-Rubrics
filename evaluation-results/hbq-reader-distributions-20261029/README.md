# Reader score distributions: Dryad DEV30 and Kyoto QSF12

This supplement adds near-extreme score rates and cached assessment coverage to the
[existing reader report](../hbq-reader-reference-descriptive-v1/README.md) and
[measurement matrix](../hbq-measurement-matrix-v1/README.md). It uses already opened
development results. No new judgments, scoring, bootstrap draws or human labels
were produced.

Scores are mapped for display as `100 * (score - original_min) / (original_max - original_min)`.
The ranges come from the frozen scoring definitions: HBQ/ladder 0–100, TTCW14
0–1, holistic 1–7, compact 1–5 and Oregon 6–36. Inclusive near-floor/ceiling
thresholds are 10/90. Missing scores are excluded from numeric denominators and
retained separately; the observed minimum and maximum never define the mapping.

| Dataset | Method | Available / planned | Near floor | Near ceiling |
| --- | --- | ---: | ---: | ---: |
| Dryad | HBQ | 28 / 30 | 0 / 28 | 0 / 28 |
| Dryad | TTCW14 | 29 / 30 | 12 / 29 | 0 / 29 |
| Dryad | Holistic | 30 / 30 | 4 / 30 | 0 / 30 |
| Dryad | Compact | 30 / 30 | 2 / 30 | 0 / 30 |
| Dryad | Oregon | 30 / 30 | 0 / 30 | 0 / 30 |
| Kyoto | HBQ | 12 / 12 | 0 / 12 | 1 / 12 |
| Kyoto | Ladder projection | 12 / 12 | 0 / 12 | 1 / 12 |
| Kyoto | TTCW14 | 12 / 12 | 0 / 12 | 0 / 12 |
| Kyoto | Holistic | 11 / 12 | 0 / 11 | 0 / 11 |
| Kyoto | Compact | 11 / 12 | 0 / 11 | 0 / 11 |
| Kyoto | Oregon | 11 / 12 | 0 / 11 | 0 / 11 |

Dryad HBQ mean cached weighted coverage is 0.980414 across its 28 numeric cases;
mean assessment-bound width is 2.245664 points on its 0–100 scale. Kyoto HBQ
coverage is 0.999567 and mean bound width 0.043950 across 12 cases. The ladder
projection uses the same parent votes. These widths describe missing rubric
assessments, not sampling confidence intervals. Scalar comparators do not save
these assessment metrics; their values are not applicable, never zero.

[report.json](report.json) also retains the exact Dryad all-five common27 view
(original30, excluded3), field-presence summaries, and six previously computed
conditional marginal intervals for the two reader axes. Their HBQ/Oregon/TTCW14
sample sizes are 28/30/29. They cannot establish paired method differences or
replace common27 results. All eight original paired and ten common-view
`interval95` values stay null; original missing-outcome bounds remain unchanged.

These are selected development cohorts with informative missingness. Kyoto has
12 stories across three topics; its available11 secondary methods do not replace
the fixed12 primary cohort. Source-to-human-delivery joins, distinct rater
identity and dependence remain limitations. Near-floor/ceiling counts alone do
not establish a better quality measure, population effect, calibration or
human reliability ceiling. No candidate or baseline is promoted.

Only aggregates and hash commitments are published. The private saved profile
caches are required to repeat the projection; this package does not claim a
public case-level regeneration route. [provenance.json](provenance.json) records
input/output commitments and the single executed projection.
