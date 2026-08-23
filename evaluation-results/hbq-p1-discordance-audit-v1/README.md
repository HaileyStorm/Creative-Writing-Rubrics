# P1 discordance audit v1

This package freezes a provider-free, private review plan for the sealed P1
same-fixture A/B holdout. It deterministically selects every target fixture
with at least one raw mismatch, binds the six already accepted singleton
receipts for each selected fixture, and writes two future singleton review
plans per fixture.

It has no execution command. `freeze`, `dry-run`, and `verify` only inspect or
write immutable local packet artifacts. Public output is aggregate-only. Any
source or packet drift leaves the audit `INCOMPLETE`; it never enables DSPy,
retries, paid fallback, prompt/rubric promotion, or reuse of the failed P1
appendix.
