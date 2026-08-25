# S1 four-state applicability treatment executor v3

V3 is a fresh provider-free successor after review of the v2 evidence protocol.
It preserves v2 unchanged and uses wholly fresh private prose, semantic mappings,
opaque artifact IDs, opaque slot IDs, and a new versioned execution root.

The candidate leaf wording and four-state 12-call geometry are unchanged. The
evidence protocol is not appended to the generic binary prompt. Instead, v3
replaces that prompt with an exact-quote-only version and supplies a strict
response schema: `kind` is exactly `exact_quote`, `exact_quote` is a nonempty
string, and `summary` must be JSON `null`. Summary evidence is unavailable.

The private absence and incomplete-evidence fixtures both contain natural text
that can be quoted verbatim. Settlement still rejects any normalization and
requires strict grounding in supplied artifact or context bytes.

All four cells must match 3/3. Success authorizes only a fresh disjoint holdout;
any complete valid miss is `NO_GO_DSPY_ELIGIBLE_ONLY`. No result automatically
promotes or changes a leaf, owner, weight, influence, prompt, or rubric.

Run `python run.py --dry-run --private-root <PRIVATE_ROOT>` to freeze the exact
prompt, schema, privacy receipt, and evidence-protocol receipt without provider
contact. Live execution remains one-shot and exact-HEAD-gated.
