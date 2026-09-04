# V13 child20 leave-one-group-out calibration diagnostic

The frozen 22-fold, 44-item TRAIN cross-validation calibration reduced
equal-group MAE from **0.890993** for uncalibrated child20 to **0.748595**
(`15.9819%` lower). It also scored below the fixed non-fitted constant-3
diagnostic (`0.776094`) by `0.027499` (`3.5432%`). Those are cross-validation
calibration readouts from one existing Grok-native score dataset, not evidence
that the child20 prompt improved.

Each fold fit six positive affine transforms on child20 rows from 21 prompt
groups, bounded slope to `[0.1, 2.0]`, intercept to `[-2, 2]`, and clipped
predictions to `[0, 5]`; the remaining group was predicted once out of fold.
The frozen calculation used Optuna `4.9.0` TPE at one worker, seed `20260904`
plus fold index, and 64 trials per fold (1,408 trials across 22 fits). All finite scores,
including zeros and false coverage flags, remained included.

The MAE result has meaningful counterevidence. Calibration won/tied/lost
14/0/8 groups and 30/0/14 items against child20, and 13/0/9 groups and 26/0/18
items against fixed-3. Pooled average-tie Spearman improved only for Relevance
and Engagement; it worsened for Coherence, Empathy, Surprise, and Complexity.
These descriptive out-of-fold ranks have no p-values and do not claim rank
preservation across fold-specific, clipped transforms.

This is development TRAIN cross-validation only: no new provider calls,
confirmation, endpoint pooling, candidate export, prompt selection, runtime,
promotion, or generalization claim follows. Native endpoint-contact cardinality
for the source dataset remains unproven. The [frozen contract](calibration-contract.json),
[implementation](calibration.py), and [aggregate result](calibration-result.json)
bind the diagnostic without publishing prompts, stories, targets, predictions,
parameters, native bodies, identities, or local paths.

Earlier optimizer packages remain as frozen historical evidence for their own
inputs and geometries; this diagnostic adds no runtime dependency or replacement
path.
