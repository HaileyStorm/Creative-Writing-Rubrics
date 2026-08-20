# Long-form evaluation synthesis

Synthesize the validated whole-work map, atomic verdicts, deterministic score reports, and task contract into reader-facing findings.

## Rules

1. Begin with enough premise, scope, and cast context for a reader who has not seen the manuscript.
2. Explain findings through IDs present in `criterion_results` and exact strings from `allowed_evidence_refs` instead of unsupported character-name assertions. Every evidence reference in a finding must belong to at least one criterion cited by that same finding; global cross-pairing is invalid. Never invent, paraphrase, or prefix an ID or reference.
3. Separate systemic patterns from isolated local defects.
4. Treat weighted author goals as scored priorities, never as hard gates.
5. Treat only validated objective, non-negotiable binding requirements as gates.
6. Respect control states. Keep observed score distinct from non-statistical uncertainty bounds caused by unassessed relevant criteria.
7. Never average chapter or sampled-unit scores. Display each local score independently and reserve whole-work conclusions for the global pass.
8. State why each finding matters and give concrete revision use, not merely a score dump.
9. Use the supplied criterion-level verdict summaries to connect each finding to actual binary judgments. Do not expose private chain of thought. Return concise findings supported by evidence references.
