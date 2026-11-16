# V13 calibration: within-prompt discrimination

The [target-only baseline analysis](../hbq-v13-calibration-target-baseline-v1/README.md)
found lower average rating error than the saved V13 calibrated model on the
same development folds. Those baselines give every item in a held prompt the
same prediction for a given dimension. This follow-up asks whether the model's
saved predictions distinguish items within a prompt; lower absolute error alone
does not answer that question.

The 44 already-open TRAIN items occupy 22 prompt groups, ten of which contain
more than one item. These ten groups yield 40 unordered within-prompt item pairs.
For each pair and each of six rating dimensions, the saved out-of-fold model
prediction is compared with the existing mean human reference. The 240
pair/dimension cells share items and are not independent observations.

| Outcome | Pair/dimension cells |
| --- | ---: |
| Reference ratings tie | 37 |
| Reference differs; model prediction ties | 115 |
| Reference differs; model orders agree | 57 |
| Reference differs; model orders disagree | 31 |

Excluding the 37 reference ties and giving a model tie half credit yields
56.4% direction agreement over the 203 remaining cells. The target-only
baselines tie every within-prompt pair and therefore receive 50% under that
same convention. Averaging the model's corresponding agreement within each
of the ten eligible prompt groups, then weighting groups equally, gives 61.0%;
these two averaging schemes answer different descriptive questions. The 115
model ties remain visible rather than being counted as decisive correct orders.

This post-result development analysis provides limited counterpoint to the
absolute-error comparison: the model distinguished some within-prompt items on
this panel despite its higher average error. It does not establish superiority,
human validation, population performance, statistical significance, or a
release decision. Pair cells share works, raters, dimensions and overlapping
training folds. The original model evidence is historical; no endpoint is
contacted or pooled for this calculation.

`regenerate.py` requires the same private digest-bound TRAIN schedule and
calibration output as the target-only analysis, along with its published source
aggregate. It checks the source commitments, reference hashes and fold
membership, reads no confirmation targets or source CSV, and writes a fresh
aggregate without source text, individual ratings or item-level predictions.
The TRAIN schedule bytes include frozen payloads; those payloads are not
decoded by the analysis. An independent ordered-pair recount reproduced all
counts and the equal-group mean.

```text
python regenerate.py --schedule <private-v13-schedule.json> --calibration <private-calibration.json> --public-result ../hbq-human-alignment-optimizer-v13-train-expansion-v1/calibration-result.json --output <new-aggregate.json>
```

Expected aggregate SHA-256:
`7bc8b4fb359c0d1887c5c26530c39b7a31d095edeb505792c733b6b0fcd19188`.
