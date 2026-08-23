# S2 disjoint passage-status holdout v1

This public package freezes the genuinely disjoint holdout earned by the
completed final-manual development settlement at `271e30a`. It makes zero
provider calls and grants no production promotion authority.

The private controller holds eight fixtures: six bounded carriers from six
distinct pre-1929 works whose authoritative Project Gutenberg records state
`Public domain in the USA.`, plus two activation controls containing no
passage. Each of the four canonical states has two fixtures. Baseline and
candidate arms receive byte-identical fixture, context, and evidence content;
only the P4 question text differs. Three repeats produce 48 future singleton
calls through owner-attested zero-charge Codex `gpt-5.6-sol` at `high`.

Fixture text, source identities, source offsets, expected states, labels, and
future responses remain private. The public package contains only commitments
and geometry. A future aggregate-only settlement may return
`PROMOTION_REVIEW_ELIGIBLE`, `NO_EFFECT`, or `NO_GO`. Even a pass requires
independent Sol review before the canonical leaf can change.

The three outcomes are exhaustive: any control mismatch in either arm is
`NO_GO`, including a baseline-only control mismatch with a perfect candidate.
`NO_EFFECT` is available only when the candidate is perfect and every control
is correct in both arms, but the two-target-state improvement floor is unmet.

Run `python run.py --dry-run` for the public provider-free validation. The
private controller has a separate provider-free verifier and sealed ledger.
