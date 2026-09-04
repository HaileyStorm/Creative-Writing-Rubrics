# V14 DSPy descendant remaining-TRAIN expansion

This development-only, in-sample Grok screen evaluates 44 remaining frozen
TRAIN items across 22 prompt groups. Every item receives a fresh matched pair:
unchanged child20 and the recovered DSPy descendant, for 88 cells. The prior
V13 baseline/child20 expansion remains immutable context and contributes no
adopted observation to this comparison.

`expansion.py` reconstructs the exact V13 remaining-TRAIN source bindings,
then uses the pinned V14 pilot to validate the recovered candidate and its
byte-identical child20 profile. It retains V10 payload formatting and delegates
preparation, native execution, finite-score response parsing, and reporting to
the pinned V13/V11 lifecycle. Preparation is provider-free; execution is
explicitly authorized, bounded to ten tasks, route/disclosure guarded, and has
no resend path.

The primary metric is six-dimension item MAE, the mean within each actual
prompt group, then an equal mean over all 22 groups. All finite 0–5 scores are
kept even when all-zero or marked uncovered. Grok and Sol are endpoint
separated; this package opens no confirmation, promotion, selection, runtime,
or generalization claim and never dispatches Sol automatically.
