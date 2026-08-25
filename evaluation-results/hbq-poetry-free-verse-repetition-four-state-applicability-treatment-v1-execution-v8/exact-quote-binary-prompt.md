# Atomic binary evaluation prompt

Apply the supplied HBQ-RS bundle to the supplied artifact and evidence packet.

For each selected question:
- return exactly one verdict: YES, NO, NOT_APPLICABLE, or CANNOT_ASSESS;
- return confidence from 0.0 to 1.0;
- provide at least one evidence item with a nonblank `reference`, `kind` set exactly to `exact_quote`, a nonblank `exact_quote`, and `summary` set to JSON `null`;
- use `exact_quote` only for a contiguous, verbatim substring of the supplied artifact or context; do not combine, normalize, or paraphrase it;
- provide a concise note of at most two sentences.
