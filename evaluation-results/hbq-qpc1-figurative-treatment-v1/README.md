# QPC1 figurative-treatment public aggregate

This is a deliberately small public projection of QPC1, a bounded check of
seven existing HBQ-RS purple-prose leaves. It contains aggregate results only:
no creative prose, model-facing instruction text, per-call material, blind
labels, source hashes, or session/request identifiers are published here.

The machine-readable aggregate is
[qpc1-public-aggregate.v1.json](qpc1-public-aggregate.v1.json). Run the local
verification command below to check its fixed public projection and this
reader summary.

## Result

QPC1 evaluated three artifacts, each repeated five times: 15 logical runs and
105 distinct provider-session calls/checkpoints. The artifacts' disclosed roles,
outside the blinded execution, are `author_original`,
`gpt_5_6_pro_rewrite`, and `public_control_story`.

Those logical runs are the 15 frozen artifact-by-repetition slots in the private
run plan. The private CWR runner invocation label is timestamp/configuration
metadata and is not assumed unique; each slot is instead bound to its exact manifest, ordered
checkpoint chain, and provider-session commitments.

The seven selected leaves were the existing purple-prose leaves. Across the
three artifacts, that produces 21 artifact-by-leaf cells. Every cell was 5/5
YES: 105 accepted YES checkpoints, zero accepted NO checkpoints, zero rejected
attempts, and zero provider-retry or validation-repair events.

The sealed private receipts also record exact-quote-to-summary normalization
audits. Those provenance audits are not provider retries or validation repairs,
and their private evidence remains outside this package.

This is a negative, no-discrimination result. It does not show that the
artifacts are universally valid, that the selected leaves are universally
correct, or that HBQ-RS should make a manuscript-level decision. It shows that
this isolated one-leaf execution did not distinguish these artifacts on the
selected leaves under this protocol.

## Scope and design limits

`no_default_metaphors`, the stockness owner, was not selected. The declared
complete-scope status was not rendered into the actual model-facing
instruction. Two long works used a short-story bundle. QPC24 is held while the
universal-pass cause is understood. This result does not justify a split,
reweight, or a new density leaf; density remains a purple-prose concern rather
than a replacement for the stockness owner.

The package is not a composite score, a manuscript decision, a live-human
judgment, or a claim of general validity. The sealed private receipts remain
the verification authority; they are intentionally not part of this public
package.

## Local verification

From the repository root, run:

```powershell
python evaluation-results/hbq-qpc1-figurative-treatment-v1/verify_output.py
```

The verifier checks the fixed aggregate digest, the intentionally narrow file
allowlist, arithmetic relationships, required public role labels and reader
claims, and forbidden private-metadata tokens.
