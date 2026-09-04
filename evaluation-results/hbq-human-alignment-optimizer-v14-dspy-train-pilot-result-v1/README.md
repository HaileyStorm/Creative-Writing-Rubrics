# V14 DSPy descendant TRAIN pilot result

This is a matched in-sample TRAIN development result for the four frozen V11
items: unchanged child20 versus one independently verified DSPy descendant.
The descendant retains child20's profile bytes and changes only the instruction.
The same eight frozen payload bytes were used for each endpoint.

Grok generated the edit from a DSPy 3.3.1-rendered TRAIN prompt. Judges were
Grok `grok-4.6` (reported `grok-4.6-build`) and OpenAI `gpt-5.6-sol`, both
requested at high reasoning. Those settings are not provider attestations.

Lower MAE is better. On Grok, child20 scored `0.625` and the DSPy descendant
scored `0.6111111111111112`, a delta of `-0.01388888888888884` (`2.2222%`;
one group win, two ties, one loss). The earlier V11 child20 value was
`0.7083333333333334`; the `0.08333333333333337` control-run shift is larger
than this pilot's Grok delta, so the pilot does not support a reliability or
significance claim.

The separate Sol comparison scored child20 at `1.163888888888889` and the
DSPy descendant at `1.0701388888888888`, a delta of `-0.09375000000000022`
(`8.054892601432%`; three group wins, no ties, one loss). A fixed non-fitted
constant-3 diagnostic scored `0.7638888888888888` on these items: worse than
both Grok candidates and better than both Sol candidates.

The pilot is development-only. It is not confirmation, generalization,
selection, promotion, runtime authority, endpoint pooling, or a claim of
absolute judge quality. No ranking statistic was measured. Grok coverage was
false for `0/48` dimension flags; Sol coverage was false for `1/48`; no score
vector was all zero. Native endpoint-contact cardinality remains unproven.

See the aggregate [result](result.json) and public-only
[provenance commitments](provenance.json).
