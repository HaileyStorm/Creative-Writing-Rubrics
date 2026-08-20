# Atomic binary evaluation prompt

Apply the supplied HBQ-RS bundle to the supplied artifact and evidence packet.

For each selected question:
- return exactly one verdict: YES, NO, NOT_APPLICABLE, or CANNOT_ASSESS;
- return confidence from 0.0 to 1.0;
- cite the minimum necessary artifact span, source ID, image region, panel, or audio timestamp;
- provide a concise note of at most two sentences;
- do not rely on a verdict for a neighboring question;
- do not infer whole-work success from an excerpt;
- do not convert missing evidence into NO;
- do not treat deliberate difficulty as accidental failure without evidence;
- do not expose private chain-of-thought.

Evaluate hard gates first. If a hard gate is NO, continue evaluating diagnostic questions unless the caller has requested early stop. Enforce the cumulative order of subjective thresholds.

Return JSONL conforming to `schema/hbq_verdict.schema.json`, one object per question.
