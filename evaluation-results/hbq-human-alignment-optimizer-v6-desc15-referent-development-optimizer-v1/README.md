# Desc15 referent result replay and development optimizer

This provider-free tool replays the exact 52-cell Grok receipt collector, independently reconstructs the thirteen HANNA development targets, computes item MAE, averages items within each of seven frozen prompt groups, and then weights those groups equally.

It runs a real 24-trial Optuna `GridSampler` over four candidates and six frozen robustness settings. A child qualifies only when its raw equal-group MAE is strictly below the descendant-13 parent and its objective is no worse than the parent under all six settings. The qualifying set is frozen before Sol; Sol can only veto. If no child qualifies, the parent is retained and no Sol calls are needed.

DSPy is used only to construct four replay-evidence examples. It makes no LM or provider calls and has no production-runtime or selection authority. The package opens no confirmation data and supports no generalization, promotion, pooled-endpoint, or runtime claim.
