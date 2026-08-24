# L2 contextual-justification treatment executor v1

This is the one-shot, treatment-only executor for frozen source `9fe172f`. It plans 18 sequential singleton Sol/high calls: six public synthetic cases, one line-break leaf, and three repetitions. It renders the six baseline prompts locally only to verify the frozen pair hashes; it never schedules or sends a baseline, necessity question, or image input.

The executor is prepared and dry-run locally before any separately authorized execution. A claim is created before the first contact; retry and resume are forbidden. Settlement is aggregate-only and requires a separate boolean scorer. All six cells at 3/3 yield `HOLDOUT_ELIGIBLE_ON_SUCCESS`; any complete valid miss yields `NO_GO_DSPY_ELIGIBLE_ONLY`; invalid or incomplete runs produce no result. It does not run DSPy or promote a rubric change.
