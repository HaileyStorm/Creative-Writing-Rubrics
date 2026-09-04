# V14 DSPy development checkpoint

This matters because the recovered DSPy instruction reduced the primary Grok
development-panel error against unchanged child20, but the same panel leaves
the simplest useful calibration baseline almost tied and gives mixed ranking
evidence.

This receipt-derived, endpoint-separated checkpoint covers 13 frozen development
items, 7 prompt groups, and 26 matched cells per endpoint. On Grok, equal-group
item MAE was
`0.9642857142857143` for child20 and `0.763888888888889` for the frozen DSPy
descendant: a `0.20039682539682535` absolute reduction (`20.78189300411522%`).
The descendant won 5 groups, tied 0, and lost 2. A fixed, non-fitted constant-3
diagnostic scored `0.7658730158730158`, only `0.001984126984126866` above the
DSPy result; this is a calibration counterexample, not a candidate or vote.

The separate matched Sol measurement was also lower for the DSPy descendant:
child20's equal-group MAE was `1.1908730158730159` and the descendant's was
`0.9607142857142857`, an absolute reduction of `0.23015873015873012`
(`19.326891036321223%`). The descendant won all 7 groups. Fixed-3 was
`0.7658730158730158` on the same reconstructed targets, so both Sol candidates
were worse than that diagnostic. Sol item-level rank correlations were higher
in 5 of 6 dimensions (all but Surprise); group-mean correlations were higher in
4 of 6 (Relevance, Empathy, Surprise, and Complexity), with Coherence and
Engagement lower. These descriptive correlations have no p-values and are not
part of the primary MAE result.

On Grok, descriptive average-tie Spearman correlations were higher for the DSPy result
in only 2 of 6 dimensions (Relevance and Surprise), and lower in the other 4,
at both the 13-item and 7-group-mean units. They have no p-values and are not
part of the primary MAE result. All Grok finite scores were retained: coverage
was false for 0 dimensions and one all-zero score vector was retained. Sol
retained all finite scores and had one false-coverage cell for each candidate;
it had no all-zero score vector. A false-coverage cell is not a count of false
coverage dimensions.

The replay checked 26 unique request identities and 26 unique session
identities, native-response/receipt digest agreement, exact schedule payload
bindings, and CSV target reconstruction. The Sol replay separately checked 26
unique request identities, 26 unique session identities, receipt inventory, and
the same schedule payload and CSV target bindings. The schedule file's
physical-byte SHA-256 is
`eaef1e6d25e4a6ac1fb4a55d5924f6c34bf651a42ba390ed581bc7ce7b4ac8c8`; its
canonical semantic schedule SHA-256 is
`de024cc4e7bd548b6a73cdbe6424f996d4ffece4399bf651c235f8ae7219a8b2`.
Those are different commitments by design. The frozen schedule binds identical
Grok and Sol payload digests. Native endpoint-contact cardinality and provider
attestation remain unproven for both endpoints.

The source is commit `3cda5ef`, development source SHA-256
`48cff43b8ba31962eaf618af1f70c18fd9581e9d59a8da62bf646cf7a2317fa8`, with
contract SHA-256
`37dd1f1a9f26dc7091bcafb7c49ddd03d891c0ec12cdab028535a89bbf679994`.
The Sol composition is commit `5c4c8e7`, SHA-256
`d407df43917b1e513cc1a7696bb04ccd292ad266e78e189771d5e8248c6a70f3`.
The compared frozen DSPy candidate is
`candidate-62195a3b90edd96d` (`62195a3b90edd96d619279b5e229f78862b971ba44d10de86468dee6badbe9e4`).

This is in-sample development evidence only. It creates no confirmation,
generalization, selection, promotion, runtime, endpoint-pooling, or automatic
Sol-dispatch authority. Older optimizer packages remain as frozen history for
different inputs; this checkpoint adds no runtime path.

Machine-readable aggregates and rank readouts are in
[development-result.json](development-result.json).
