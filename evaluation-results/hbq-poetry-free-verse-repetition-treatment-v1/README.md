# HBQ-RS free-verse repetition treatment v1

This r3 package is a provider-free, development-only freeze for a same-fixture A/B screen
of `form.poetry.free_verse.repetition`. It commits four private synthetic
fixtures, two question inputs, and three repetitions each: 24 future singleton
calls. No provider calls are made by this package.

The candidate is the smallest reviewed wording treatment. It preserves the
leaf ID, owner, polarity, weight, influence, and all non-text question fields.
Fixture text, oracle labels, arm mapping, and repeat mapping remain in the
private controller. Public slot IDs are deliberately opaque and are never
rendered into a provider-facing prompt.

The private gate requires 12/12 candidate matches, including the target and
all controls, plus a current-wording target result of at most 2/3. The private
verifier must derive that gate from terminal slot records; a summary boolean
attestation is not accepted. A pass authorizes only a disjoint holdout; it does
not promote the candidate. The unexecuted r1 and r2 private freezes are
retained only as provenance.

Run `python run.py --dry-run` to verify the public commitments and opaque
schedule without contacting a provider.
