# V15 Grok TRAIN checkpoint: weak rank alignment

The completed Grok measurement does **not** establish a successful HANNA judge. On the frozen 48-story TRAIN panel, direct integer scoring reached a six-criterion, item-level tied-Spearman macro of `0.20311136989621129`; cumulative ordinal thresholds reached `0.1728341673770619`. Both are weak. This is development-only evidence, not a CWR runtime, promotion, confirmation, or full-rubric result.

The measurement contains 96 matched cells: 48 stories in 24 unequally sized prompt groups, evaluated once under each output form. Every finite score and coverage value was retained. The primary MAE is first computed per item across six criteria, then averaged within each scheduled prompt group and equally across the 24 groups.

| Output form | Primary rank macro | Equal-group MAE | Fixed-three MAE context |
| --- | ---: | ---: | ---: |
| Direct integer 1–5 | 0.203111 | 0.952739 | 0.777778 |
| Four cumulative thresholds | 0.172834 | 0.925386 | 0.777778 |

Thresholds reduce MAE by `0.0273533950617284` versus direct scores, but worsen the primary rank measure and both forms have higher MAE than the fixed-three control. Lower error alone is therefore not an improvement claim here.

## Criterion-level rank association

| Criterion | Direct integer | Ordinal thresholds |
| --- | ---: | ---: |
| Relevance | 0.530289 | 0.588486 |
| Coherence | 0.132640 | 0.050722 |
| Empathy | 0.115559 | 0.152978 |
| Surprise | -0.258765 | -0.287078 |
| Engagement | 0.350339 | 0.372070 |
| Complexity | 0.348605 | 0.159827 |

Score occupancy is especially compressed for Surprise: score 1 appears for 45 of 48 direct cases and 44 of 48 threshold cases. That is a descriptive feature of this panel, not an explanation that turns weak rank association into success.

## Evidence and limits

The judge was Grok Build: requested `grok-4.6` / `high`, reported `grok-4.6-build`; accepted reasoning effort was not independently attested. These are ratings of existing HANNA stories, not newly generated stories.

The native report completed with 96 unique recorded request identifiers and 96 unique recorded session identifiers. An independent provider-free raw-response arithmetic replay matched the native report. These are evidence-integrity checks, not provider-identity attestation or a claim about behavior beyond this study.

The local targets are averages of three human labels. Omitting them from outbound payloads prevents target leakage; it does not establish model–human agreement. The comparison is a reference-free HANNA adaptation on frozen TRAIN stories, not the original HANNA design of ten systems/stories per prompt with three human raters or an exact replication of the paper's human annotation setup. It is not comparable to the paper's larger samples and does not establish CWR-wide human alignment. The separate Sol native report and independent arithmetic replay both completed with a match; it is not pooled with Grok. See [SOL_TRAIN.md](SOL_TRAIN.md).

Machine-readable aggregate: [grok-train-result.json](grok-train-result.json).
