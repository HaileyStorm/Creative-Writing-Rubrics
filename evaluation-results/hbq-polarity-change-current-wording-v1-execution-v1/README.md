# P1 polarity current-wording execution v1

This is the separately frozen, zero-paid execution successor for the public
synthetic P1 current-wording screen at `5665e2f`.  It schedules 132 singleton
calls (eleven leaves, four-state fixtures, three repetitions) and permits at
most 396 cumulative provider sends.  It does not contain results, expected
labels, raw responses, or private schedules.

Preparation writes every synthetic input, the private expected-label ledger,
and a frozen private P1 diagnostic bundle outside the checkout.  `--dry-run`
uses the ordinary CWR direct-judge path and makes zero provider calls.
`--execute` and `--resume` require both `--allow-remote` and
`--acknowledge-zero-incremental-charge`; the route is Codex,
`gpt-5.6-sol` at `high`, with one leaf per call and three cumulative attempts.
No paid API or fallback provider is permitted.

Rendered prompts are frozen as canonical UTF-8 LF bytes.  The CWR checkpoint
comparison applies only the explicit CRLF/CR-to-LF transport normalization on
both sides, records raw and canonical hashes, and rejects every other byte
difference.  This avoids Windows text-mode line-ending false failures without
loosening prompt identity.

The external settlement is four-state.  YES, NO, and CANNOT_ASSESS cells must
match all three repetitions for `PASS_NO_CHANGE`; NOT_APPLICABLE cells are
completed diagnostics and are not pass-scored.  Public output is aggregate-only
and no prompt, rubric, leaf, ownership, split, or weight change is promoted.
