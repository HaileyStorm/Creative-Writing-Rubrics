# V15 Sol TRAIN checkpoint: thresholds help, but remain weak

Sol completed the separate matched 96-cell native measurement over the same 48 frozen TRAIN stories and 24 unequally sized prompt groups. Cumulative ordinal thresholds improve Sol's primary six-criterion, item-level tied-Spearman macro from `0.16748418077773755` to `0.26357633418906495`. That is still weak alignment evidence, not a successful judge or a CWR promotion result.

| Output form | Primary rank macro | Equal-group MAE | Fixed-three MAE context |
| --- | ---: | ---: | ---: |
| Direct integer 1–5 | 0.167484 | 0.906134 | 0.777778 |
| Four cumulative thresholds | 0.263576 | 0.843519 | 0.777778 |

Thresholds lower Sol MAE by `0.0626157407407408` versus direct scores and improve its primary rank metric, unlike the completed Grok endpoint. Both Sol forms nevertheless have higher MAE than fixed three. Endpoint disagreement is reported as a limitation, never pooled into a winner.

## Criterion-level rank association

| Criterion | Direct integer | Ordinal thresholds |
| --- | ---: | ---: |
| Relevance | 0.598253 | 0.587560 |
| Coherence | 0.086339 | 0.176779 |
| Empathy | 0.058037 | 0.143932 |
| Surprise | -0.142135 | -0.168430 |
| Engagement | 0.036919 | 0.459841 |
| Complexity | 0.367492 | 0.381775 |

The local targets are averages of three human labels. Their omission from outbound payloads prevents target leakage; it does not itself show model–human agreement. This remains a reference-free HANNA adaptation on TRAIN stories, not the original HANNA design of ten systems/stories per prompt with three human raters and not a comparison with the paper's larger samples.

The native report and independent 96-cell arithmetic replay are complete and match. The judge was requested as `gpt-5.6-sol` / `high` through the local Codex subscription route; the native output does not independently attest model or accepted effort. These are ratings of existing HANNA stories, not newly generated stories. Grok and Sol remain separate results with no endpoint pooling, selection, promotion, confirmation, runtime, or generalization conclusion.

Machine-readable aggregate: [sol-train-result.json](sol-train-result.json). The separate [Grok checkpoint](GROK_TRAIN.md) remains available for endpoint-specific context.
