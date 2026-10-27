# Five-module macro: lower development correlations

The experimental `five_module_report_macro_v1` had lower observed correlations
with the existing TTCW expert reference than full HBQ on both fixed development
cohorts. These results provide no reason to advance this macro or change defaults.

| Fixed development cohort | Five-module macro | Full HBQ | Raw type/token ratio |
| --- | ---: | ---: | ---: |
| 29 complete HBQ banks | 0.540315 | 0.686260 | 0.783309 |
| 28 works shared by all five benchmark methods | 0.538874 | 0.711917 | 0.780750 |

Values are average-tie Spearman correlations. HBQ and text-control results are
reused from the [source-control analysis](../hbq-sol-ttcw-source-controls-20261026/README.md)
at exactly the same membership. The human reference is the fraction of YES
ballots across fourteen tests and three ballots per test. It is not a direct
preference label or 42 independent experts.

The new macro combines five modules with these fixed weights:

| Component | Weight |
| --- | ---: |
| Freshness and non-genericness | 0.5 |
| Economy and relevance | 2 |
| Specificity and embodiment | 0.5 |
| Language craft | 0.5 |
| Purple-prose avoidance | 1 |

Each component is its effective leaf-weighted YES fraction among YES and NO
answers. The macro is 100 times the weighted mean, with fixed denominator 4.5.
Purple-prose avoidance is a positive factor here. This is a new formula, distinct
from the canonical domain normalization and capped penalty calculation.

The projection uses existing complete, strictly admitted 178-question reports
and retains their hard gates and global numeric eligibility. It selects 38
leaves per bank. NOT_APPLICABLE leaves are excluded; CANNOT_ASSESS remains
unknown. An undefined factor makes the macro unavailable without dropping or
reweighting factors. All 29 observed macros were numeric, and their selected
leaves contained no CANNOT_ASSESS answers. Sensitivity bounds therefore had zero
width in this sample; they are not confidence intervals.

This is post-result development work. The weights came from an earlier
opened-label selection, and this contrast followed earlier benchmark and
control results. Economy and purple avoidance together receive two thirds of
the weight and overlap in concision and restraint. Selection, length and lexical
confounding remain strong objections. Seven of the planned 36 banks are missing,
the original 33-work rule is unmet, and the works share twelve plot groups.
No population inference, confidence intervals, confirmation or promotion follows.

The run made 29 report projections and two new correlations. It made no model
requests, native receipt replays, canonical scoring or compilation calls, and
created no labels or votes. [analysis.json](analysis.json) retains aggregate
results and source commitments. Individual data and private provenance remain local.
