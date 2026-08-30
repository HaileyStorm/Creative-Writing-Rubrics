# Balanced DSPy HANNA held-out evaluation v1

This package freezes a provider-free, paired held-out schedule for ten reconciled Grok descendants and the exact pinned v3/balanced baseline (`candidate-52d1be4bc34e0018`). It uses four prompt-group-disjoint development groups from the frozen Fresh88 48/13/19 split; two are also the Sol sprinkled subset. The schedule is 66 fresh cells: 11 candidates times four Grok groups plus two Sol groups.

Each cell carries exact versioned payload bytes. Matching item/candidate cells have byte-identical payloads across Grok and Sol. Only the candidate instruction/profile may change between candidate payloads. Missing, malformed, or terminal cells block that candidate/route; nothing may be replaced or resent.

`analyze.py` has no provider, DSPy, or Optuna dependency. It independently regenerates the schedule from the one pinned reconciler manifest (file SHA-256 `26b91ea23f04b55909db775b75c1bf7ae2d4819d2acc8346244548296e229bf3`; internal SHA-256 `8184c85e3be49669b8d3c1c28702b531e7a7bc501297252e4c8b8f87fb08f2ac`), audited normalized descriptors, the frozen successor, and the HANNA CSV before rejecting execution. It replays the pinned reconciler into a fresh temporary directory and requires byte-identical output. The reconciler source/contract, original terminal-root counters, and zero-contact reconciliation counters remain explicit; terminal roots are not relabeled as a different execution.

The versioned [held-out executor](../hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-exec-v1/)
subsequently settled all 66 scheduled cells: 44 Grok cells across the four
development groups and 22 Sol local-lifecycle cells across the two matched
groups. Grok-primary selection was frozen before Sol evidence was opened.
`candidate-0ca942ad28cb4104` reduced Grok MAE from `1.069444` to `0.875`, but
the unchanged candidate increased Sol MAE from `1.368056` to `1.427778`.

The endpoints are not pooled. This is a model-specific Grok development
improvement and a Sol reversal, not independently observed cross-endpoint
gain. Sol local lifecycle is verified, while native endpoint/contact
cardinality remains unproven. Confirmation remains unopened; DSPy and Optuna
remain development-only and have no runtime or confirmation authority.
