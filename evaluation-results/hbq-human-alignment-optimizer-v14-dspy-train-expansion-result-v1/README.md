# V14 DSPy descendant TRAIN expansion result

This public packet reports a matched in-sample TRAIN expansion over 44 frozen
TRAIN items, 22 prompt groups, and 88 cells per endpoint. It compares unchanged
child20 with the same independently verified DSPy descendant and shared profile
used in the V14 pilot. Both endpoint replays retained exact payload/CSV parity;
all 88 Grok receipts, native responses, and unique request-session IDs were
present with no anomalies.

Lower MAE is better. On Grok, child20 scored `0.8842592592592592` and the DSPy
descendant scored `0.7525042087542088`, a delta of `-0.13175505050505043`
(`14.9000%`; 29 item wins, 7 ties, 8 losses; 17 group wins, 2 ties, 3
losses). Against fixed-3, the DSPy descendant's W/T/L was `21/2/21` by item
and `10/1/11` by group; its aggregate MAE was lower, while child20's was
higher. Grok false coverage flags were `0/528`; no score vector was all zero.

On Sol, child20 scored `1.1681755050505052` and the DSPy descendant scored
`1.0232617845117844`, a delta of `-0.14491372053872076` (`12.4051%`; 17 group
wins, no ties, 5 losses). A fixed non-fitted constant-3 diagnostic scored
`0.7760942760942761`, better than both Sol candidates. Sol false coverage
flags were `2` for child20 and `4` for the descendant out of `264` each; no
score vector was all zero.

Post-hoc Grok rank readouts improved on `3/6` item-level dimensions
(Relevance, Empathy, Complexity) and `4/6` group-level dimensions (Relevance,
Empathy, Surprise, Complexity). The separate Sol readouts improved `2/6` in
each view. These are mixed discrimination readouts, not universal ranking
evidence.

The two endpoint results remain separate development follow-up only. This
packet is not confirmation, generalization, selection, promotion, runtime
authority, or endpoint-pooling evidence; native contact cardinality and
attestation remain unproven.

The proposal used real DSPy `3.3.1`; its generator and judging settings are
recorded as requested/reported context, not provider attestations or a runtime
dependency. See the aggregate [result](result.json) and public-only
[provenance commitments](provenance.json).
