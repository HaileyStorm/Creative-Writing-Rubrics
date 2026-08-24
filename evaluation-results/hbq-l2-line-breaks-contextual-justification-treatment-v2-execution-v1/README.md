# L2 material-context treatment executor v1

This is the one-shot, candidate-only executor for frozen source `fd96e80`. It prepares exactly 18 sequential singleton Sol/high text calls: six public synthetic cases, the line-break leaf only, and three repetitions each. It verifies the six frozen canonical/candidate prompt pairs locally, but never schedules or sends a canonical prompt, necessity leaf, or image.

The frozen v1 terminal lifecycle is loaded from its pinned blob and validates the package, prepared manifest, runtime schedule, subscription receipt, and disclosure before creating an execution claim or contacting a provider. There is one physical attempt per slot: retry and resume are forbidden. Response normalization follows the canonical quote-to-summary policy.

Settlement accepts only an external boolean scorer after complete terminal execution. It preserves a complete 0/1/2/3 cell histogram privately, emits only aggregate public data, and writes the claim-bound settlement/publication marker. Six 3/3 cells yield `HOLDOUT_ELIGIBLE_ON_SUCCESS`; any complete valid miss yields `NO_GO_DSPY_ELIGIBLE_ONLY`; invalid or incomplete execution yields no result. It implements neither DSPy nor promotion.
