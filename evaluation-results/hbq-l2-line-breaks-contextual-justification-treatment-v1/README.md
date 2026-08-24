# L2 contextual-justification wording treatment v1

This is a provider-free freeze that renders six canonical-versus-candidate prompt pairs. It does not run an evaluation. The only rendered difference is the line-break question text.

The candidate preserves the line-break leaf's ownership and weight. It strengthens the positive-evidence standard by requiring an immediate-context explanation, while explicitly excluding a pause, interruption, or repeated pattern as sufficient evidence on its own.

The protected outcome ledger is never incorporated into a rendered prompt. A later, separately authorized treatment-only screen has exactly six cells and three singleton repetitions per cell (18 calls). All six cells at 3/3 would make the candidate holdout-eligible; any complete valid miss is `NO_GO_DSPY_ELIGIBLE_ONLY`; an incomplete or invalid run is no result. This package creates neither an execution surface nor a promotion.

Lineage binds the public text-only L2 result at `f1dd530`, its executor at `b7a3f8e`, its freeze at `1290b6e`, and the pinned production runtime and compiled line-break leaf.
