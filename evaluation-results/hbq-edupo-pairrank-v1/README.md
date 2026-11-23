# Rank agreement in an exposed Czech poetry study

This retrospective development analysis uses the released 100-row EduPo table
from [Mareček et al. (2025)](https://aclanthology.org/2025.eval4nlp-1.9/).
It compares the table's human and historical ChatGPT scores for the same rows;
there are **no CWR scores** in this analysis. The paper identifies the model
as GPT-4o mini. The poems are Czech, selected for rhyme and metre, and comprise
five source groups of 20. They do not represent free verse or a general poetry
population. This cohort and its individual annotations have been exposed to
the CWR task and are not unused confirmation data.

| Dimension | All 4,950 pairs: tau-b | Within-source 950 pairs: tau-b | Within-source strict agreement |
| --- | ---: | ---: | ---: |
| Semantics | 0.515 | 0.227 | 281 / 421 = 66.7% |
| Syntax | 0.467 | 0.053 | 232 / 430 = 54.0% |
| Rhyming | 0.224 | 0.205 | 276 / 422 = 65.4% |
| Metre | 0.427 | 0.283 | 295 / 412 = 71.6% |

Kendall's tau-b includes tie adjustment. Strict agreement is concordant pairs
divided by pairs that **both** human and model rank strictly; ties are excluded
from that denominator, not counted as agreements. Within-source tau-b pools
the pair counts from the five groups; it is not the mean of five separate
correlations. The full [aggregate](aggregate.json) gives concordant,
discordant, human-only tie, model-only tie and joint-tie counts, separately for
all, within-group, between-group and each source group. The 4,950 pairs share
only 100 poems and are not independent observations. Differences between the
pooled and within-group descriptions do not establish a causal source effect,
and the analysis was chosen after the data were exposed.

For the four dimensions, respectively, 22, 23, 31 and 2 of the 100 human
values equal the stated 0–10 scale maximum; zero model values equal the stated
normalized maximum of 1. These are exact endpoints, not near-ceiling rates or
evidence that the two assessors use equal anchors. The paper reports three
experts averaged for semantics and one per other human metric, including a
replacement metre rater; the table alone does not authenticate each value's
transformation or individual rater provenance. The paper also analyzes
human-written and generated subsets and notes limits of its model evaluator;
this pairwise description is not an independent replication of the study.

The table's path/poem binding and historical execution remain qualified in the
[source check](../hbq-edupo-source-group-v1/README.md). No new provider calls,
poem texts, human labels, CWR judgments or model judgments were generated. The
result is not evidence of CWR alignment, a strong contemporary comparator,
population generalization, statistical significance, or a release gate.

To reproduce, obtain the authors' `evaluation/annotations/all5.tsv` at commit
`5740fbc2f7f32bf3257d5baf69747ad9958dc5ec` and run
`python analyze.py <path-to-all5.tsv>`. The program verifies its SHA-256 and Git
blob, requires the expected group counts and score ranges, parses paired rows,
and outputs aggregate counts without individual rows or poem text. A separate
contingency-table recount matched all pooled, within- and between-group pair
counts; the source table itself is not included in this package.
