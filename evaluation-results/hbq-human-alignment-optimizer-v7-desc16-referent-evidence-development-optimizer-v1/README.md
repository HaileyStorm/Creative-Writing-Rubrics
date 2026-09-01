# Desc16 referent-evidence result replay and development optimizer

This provider-free analyzer replays the exact frozen 52-cell Grok receipt collector and independently reconstructs the thirteen development-only HANNA targets. It computes item MAE, averages items inside each of seven frozen prompt groups, then gives every group equal weight.

It evaluates all three desc16 children only against the committed desc15 child-20 parent. A child must be strictly better on raw equal-group MAE and no worse under each of six frozen robustness settings. The resulting Grok qualifiers are frozen before any Sol work; Sol may veto a qualifier but cannot select an unqualified alternative. If none qualify, child-20 remains and Sol receives zero cells.

DSPy constructs replay-evidence examples and Optuna runs the 24-trial GridSampler robustness sweep during development only. Neither makes LM calls or has runtime-selection authority. The package binds the desc16 candidate freeze commit, schedule, and manifest; it admits the executor bytes at replay time and writes their exact hash into the result. No confirmation, reserve, private input, promotion, pooled-endpoint, runtime, or general claim is supported.
