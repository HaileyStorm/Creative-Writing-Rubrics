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

If the separately reviewed adapter is ever authorized, its exact frozen
contract hash is bound into the arming receipt before a callback can run. Each
callback starts at most one model-contact process. A failure before the process
starts is recorded as recoverable `PRECONTACT_FAILED_NO_MODEL_CONTACT`; it does
not create a review run or authorize a later review. The same callback may be
retried from the same evidence root, using the next contiguous attempt name.
Its envelope reports zero starts for that callback while the study result keeps
the cumulative count of earlier accepted callbacks. The exact review ID and
arming-receipt hash are bound into every request. Any uncertainty after process
start is terminal `AMBIGUOUS_NO_RETRY`. The package reports requested
model-contact processes separately from observed starts, and reports provider
HTTP attempts as unknown because Codex JSONL does not expose them. Requested
model and reasoning remain configuration, not provider-attested identity.
Successful private preflight, contact, and external-evidence files are
reconciled by hash before acceptance and again at settlement; their public
projection stays aggregate-only.
