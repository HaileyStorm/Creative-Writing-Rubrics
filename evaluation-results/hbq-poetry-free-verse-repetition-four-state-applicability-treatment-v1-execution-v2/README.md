# S1 four-state applicability treatment executor v2

This v2 provider-free successor repairs the v1 identifier-boundary defect.
The v1 private root rendered twelve prompts but made zero provider calls and
created no execution claim; it remains stale historical evidence.

V2 keeps semantic fixture keys, state mapping, expected labels, and shuffled
repeat mapping only in the external private controller and ledger. Before prompt
construction, each fixture becomes an unrelated opaque artifact token. Slot IDs
are independently opaque and are not rendered into provider prompts.

The exact manual treatment, four-state 12-call geometry, Sol/high singleton
route, first-attempt policy, strict quote grounding, zero-normalization gate,
and outcome policy are otherwise unchanged. A prompt-privacy receipt proves
that no private semantic fixture ID, state token, oracle field, expected-label
binding, or rationale marker appears in any frozen provider prompt.

All four cells must match 3/3. Success authorizes only a fresh disjoint holdout;
any complete valid miss is `NO_GO_DSPY_ELIGIBLE_ONLY`. No result automatically
changes the leaf, owner, weight, influence, prompt, or rubric.

Run `python run.py --dry-run --private-root <PRIVATE_ROOT>` to freeze provider
bytes and the privacy receipt without contact. Live execution requires both
explicit acknowledgements and exact source HEAD `6ae9ee0` at the claim boundary.
