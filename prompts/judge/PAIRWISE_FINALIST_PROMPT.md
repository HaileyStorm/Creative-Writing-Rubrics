# Pairwise finalist adjudication prompt

You receive two candidates that have already passed hard gates and received independent HBQ-RS reports.

1. Verify that both reports used the same bundle, profiles, and evidence scope.
2. Compare only the dimensions that materially distinguish the candidates.
3. State explicit tradeoffs with evidence from both candidates.
4. Do not treat length, formatting, or rhetorical confidence as quality unless relevant.
5. Use the active user-taste overlay only after craft and task eligibility are reported.
6. Return TIE when the evidence does not justify a stable choice.
7. The caller must repeat the judgment with candidate order swapped; disagreement triggers escalation.

Output: eligibility status, distinguishing criterion IDs, concise A/B evidence, preference A/B/TIE, confidence, and escalation recommendation. Do not provide private chain-of-thought.
