# Mapped-score development calibration: negative result

This matters because a learned calibration can lower error without showing that
the underlying HBQ mapped features add value. Here, a no-feature TRAIN target
prior did better than the learned ridge calibration, so the feature-value claim
fails on this diagnostic.

The provider-free study used 48 TRAIN items in 24 leave-one-prompt-group-out
folds, with 23 fitting groups per fold. Its primary metric is item absolute
error, then group mean, then equal mean across the 24 groups. All four frozen
arms were evaluated as follows:

| Arm | Equal-group MAE |
| --- | ---: |
| Fixed 3 | `0.7777777777777777` |
| Diagnostic `1 + 4p` | `1.1057947530864196` |
| Positive affine mapped score | `0.8816612086157968` |
| Ridge residual mapped score | `0.6206068094466785` |

The post-hoc no-feature comparator predicts each held-out dimension from the
mean of its 23 fitting-group means, using fixed-3 only for a missing mapped
dimension. It achieved `0.544949622025407` equal-group MAE (group-weighted
lower median MAE `0.55625`), below ridge. It was not a frozen primary arm and
has no selection authority, but it is decisive negative context: this run
demonstrated no advantage of mapped HBQ features over learned TRAIN priors.

The ridge's pooled out-of-fold average-tie Spearman values were negative in
4/6 dimensions (Coherence, Empathy, Relevance, Surprise). Those predictions
come from fold-specific calibrators; the prior is constant within each fit.
Neither is story-ranking evidence, and the correlations are descriptive only.

The features were six mapped YES fractions over 27 unique leaves, not all
rubric module weights and not the canonical final HBQ score. The run used real
Optuna `4.9.0`: 24 folds × 64 TPE trials (`1,536` total), plus 24 ridge fits,
with no model calls. The source is `1599655`, SHA-256
`d0c0509f64412e9c02009c3e7ab06f8c39c7e95ccf6798366faf022ec78cbc2e`; the
contract and result hashes are in the machine-readable aggregate.

This is TRAIN-only, post-hoc diagnostic evidence. It opens no confirmation
access and authorizes no runtime, selection, promotion, feature, rubric-weight,
or canonical-score change.

See [development-calibration-result.json](development-calibration-result.json)
for compact provenance, metrics, and rank diagnostics.
