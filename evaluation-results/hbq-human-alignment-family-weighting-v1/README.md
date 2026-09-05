# HBQ family-weighting diagnostic v1

This provider-free, development-only diagnostic asks whether a small set of
relative HBQ family weights better tracks the frozen Fresh88 TRAIN human signal
than the historical all-one tree. It changes no source material: it reconstructs
the verified historical verdicts and rescoring context, then varies only the
`core`, `craft`, and `form` family multipliers.

## Frozen inputs and bindings

The authoritative entry point is `study.run_from_sources`. It accepts and
hash-binds these immutable inputs before it can fit:

- the Grok-primary development split manifest (`SHA-256`
  `6ffa942b595449f4118c2cd51f3a36716126612a7c10f4765953c17eb1efdbc2`);
- its execution freeze (`4005c941d202d1aebcc31df658093421d3677bf3033939ea5ef42e34248e9a69`);
- the Fresh88 execution contract (`6b3bfcd2407442c9997631cd38d7df7e01bd5017782feb62ad360840399b1726`);
- the pinned HANNA annotations CSV (`ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b`); and
- the Fresh88 native-run root, whose selected runs are independently verified
  and whose source, prompt, task, schedule, verdict, and runtime commitments
  are retained per record.

The package also pins its contract and source adapter. Reconstruction must yield
exactly 48 TRAIN items in 24 prompt groups and reproduce every historical
all-one final score exactly before fitting is allowed.

## Protocol

Each fold leaves one prompt group out. On the remaining groups, Optuna 4.9.0
uses deterministic TPE (`seed = 20260904 + fold`, one local job) for 128 trials
to choose each active family multiplier in `[0.5, 2.0]`. The objective is
pooled TRAIN-item average-tie Spearman against the mean of the six HANNA
dimensions, plus a small log2-distance-from-one penalty. Within-group Spearman
is retained only as context, not the fitting objective.

The reported out-of-fold comparison includes the fitted profile and three
controls: the pinned historical all-one tree, a fixed score of three, and an
equal-prompt-group human prior calculated only from each fold's training data.
It reports pooled Spearman, global and equal-group MAE, plus per-axis
descriptive Spearman and MAE for Relevance, Coherence, Empathy, Surprise,
Engagement, and Complexity.

## Measured TRAIN result

The [completed aggregate](result.json) does not support changing family weights.
All 24 leave-one-prompt-group-out folds completed 128 Optuna trials each
(3,072 total), with no new provider calls. Independent source reconstruction
reproduced all 48 historical scores and all fitted out-of-fold scores exactly.

| Metric | Historical all-one | Fitted out-of-fold |
| --- | ---: | ---: |
| Pooled Spearman | -0.105024 | -0.092254 |
| Global MAE | 1.036863 | 1.048511 |
| Equal-prompt-group MAE | 0.973766 | 0.991439 |

The small upward rank movement remains negative, and both error measures
worsen. These metrics compare the rescaled final HBQ score with the mean of
the six human dimensions; they are not the six separate-dimension prompt
metrics used by other HANNA experiments. Fixed-three and fold-training-only
human-prior controls both have lower MAE. No winning global profile was frozen.

## Limits

This package has no confirmation partition, genre or
format interaction model, model prior, runtime dependency, selection authority,
or promotion authority. The result is a TRAIN-only development diagnostic:
it cannot alter runtime weights or support a general HANNA-improvement claim
without a separately frozen, independently recomputable evaluation.
