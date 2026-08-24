# S2 disjoint passage-status holdout executor v1

This package is the one-shot execution surface for the provider-free freeze in
`../hbq-nonpoetry-scope-disjoint-holdout-v1/`. It prepares 48 singleton Codex
subscription runs: eight sealed fixtures, two wording arms, and three repeats.
The model is `gpt-5.6-sol` at `high`; paid API and fallback routes are forbidden.

Preparation and execution never open the separate expected ledger. The remote
disclosure contains the exact artifact, contexts, task contract, one-leaf
registry overlay, and rendered prompt for each slot, but never fixture state,
expected verdict, gate role, rationale, title, author, ebook number, locator, or
license metadata. Baseline and candidate prompts differ only in the frozen P4
question wording.

Live execution first creates a permanent, filesystem-atomic root claim. A
concurrent or second invocation fails before any provider-capable callback.
Any unresolved live start or nonzero process exit terminalizes this private
root and forbids retry. The claim survives crashes and settlement; a versioned
successor is required. Settlement first
requires the exact retained claim, then opens the sealed ledger only after all
48 accepted terminal receipts are verified. The private and public settlements
carry the claim hash. Public output contains aggregate counts and one of
`PROMOTION_REVIEW_ELIGIBLE`, `NO_EFFECT`, or `NO_GO`; it never promotes the
leaf.

Provider-free review:

```powershell
python run.py --dry-run --private-root <external-private-controller-root>
```

Live execution additionally requires both `--allow-remote` and
`--acknowledge-zero-incremental-charge`. No provider call is made by the dry
run.
