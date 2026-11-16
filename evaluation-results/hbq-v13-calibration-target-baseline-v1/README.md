# Target-only baselines for the V13 calibration diagnostic

This retrospective analysis adds two simple comparators to the previously
published [V13 child20 calibration](../hbq-human-alignment-optimizer-v13-train-expansion-v1/CALIBRATION.md).
On its 44 already-open TRAIN items and 22 prompt-group folds, a predictor that
uses only the training ratings had lower error than the saved model-score
calibration. This is a development diagnostic, not independent confirmation or
evidence that a target-only rule will generalize.

| Out-of-fold prediction | Equal-prompt-group mean absolute error |
| --- | ---: |
| Saved calibrated child20 scores | 0.748595 |
| Training-group target mean | 0.554012 |
| Training-group target median | 0.524916 |

Errors are in the original dimension-rating units. They average the six
dimensions within each item, then items within each held prompt, then the 22
prompts equally. The saved calibration comes from a historical Grok endpoint;
no endpoint is contacted or pooled in this analysis. It is the same historical
model-based result, including its original receipt limitations.

Each target-only prediction is fitted separately for each dimension from the
other 21 prompt groups. Each training group receives equal total weight, even
though the 22 groups contain different numbers of items. The median is the
weighted median, using the midpoint at an exact half-weight boundary. Neither
baseline uses the held group's targets or any model scores. The calibrated
model has higher held-group error than the training mean in 18 groups and lower
in four; against the training median it has higher error in 19 and lower in
three. This comparator was chosen after the original results were known and was
not a frozen primary arm.

Overlapping folds, shared raters and prompt-related items limit interpretation.
The values do not establish a population comparison, calibrated absolute
quality, a prompt improvement, a promotion decision or judge-confidence
calibration. The target-only baseline may benefit from regularities in this
particular training panel. No story, individual rating, per-item prediction,
native response or private path appears in this package.

The portable command below requires the original private, digest-bound V13
TRAIN-only schedule and saved calibration output, plus the published V13
calibration aggregate. It verifies the schedule commitment, target hashes,
fold membership, geometry and the saved calibrated MAE before writing a new
aggregate; existing output is not overwritten. It reads no original source CSV,
confirmation data or provider service. The full schedule bytes include its
previously frozen payloads; the analysis does not decode them.

```text
python regenerate.py --schedule <private-v13-schedule.json> --calibration <private-calibration.json> --public-result ../hbq-human-alignment-optimizer-v13-train-expansion-v1/calibration-result.json --output <new-aggregate.json>
```

Expected output SHA-256:
`c81f5ed34c7f270c5c3ec4e6411e4e6dc5170f56d168802764fbecdcad1fd2e3`.
An independent calculation used group means and a replicated weighted median;
it reproduced all 22 held-group comparisons and the three aggregate MAEs.
