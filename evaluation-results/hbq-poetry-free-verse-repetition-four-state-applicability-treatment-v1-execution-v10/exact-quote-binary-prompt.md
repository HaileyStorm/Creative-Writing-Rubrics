# Atomic binary evaluation prompt

Apply the supplied HBQ-RS bundle to the supplied artifact and evidence packet.

For each selected question:
- return exactly one verdict: YES, NO, NOT_APPLICABLE, or CANNOT_ASSESS;
- return confidence from 0.0 to 1.0;
- provide at least one evidence item with a nonblank `reference`, `kind` set exactly to `exact_quote`, a nonblank `exact_quote`, and `summary` set to JSON `null`;
- use `exact_quote` only for a contiguous, verbatim substring of the supplied artifact or context; do not combine, normalize, or paraphrase it;
- provide a concise note of at most two sentences;
- do not rely on a verdict for a neighboring question;
- do not infer whole-work success from an excerpt;
- do not convert missing evidence into NO;
- do not treat deliberate difficulty as accidental failure without evidence;
- do not expose private chain-of-thought.

Evaluate hard gates first. If a hard gate is NO, continue evaluating diagnostic questions unless the caller has requested early stop. Enforce the cumulative order of subjective thresholds.

Return one verdict object per question, conforming to the supplied response schema, in the JSON or JSONL envelope requested by the caller. If the caller does not specify an envelope, return JSONL.
