# Figurative scope DSPy successor v1

This is a frozen, development-only prompt-search package.  It is the successor
to the non-promoted manual scope treatment.  It may search one static
scope/materiality instruction block, but it cannot edit HBQ-RS leaves, IDs,
weights, bundles, schemas, task contracts, or runtime configuration.

The checked-in verifier and dry run make no provider calls and do not import
DSPy.  Execution is deliberately separate: it requires the Palimpsest
development virtual environment, the Codex CLI route, an explicit remote-use
flag, and the owner's zero-incremental-charge acknowledgement.  API,
OpenAI-compatible, LiteLLM, and fallback routes are forbidden.

The optimizer gets only the frozen predecessor development/selection cells. It
can propose at most four instruction candidates, with separate caps of 80
train and 32 selection calls. The public synthetic corpus is already visible;
only its private oracle is gated. A selected prompt must be hashed, frozen, and
independently approved before that oracle may be opened. Confirmation is exactly
168 singleton calls (two arms, 28 cells, three repeats) and is not authorized
by this package's dry-run mode.

`no_default_metaphors` remains the stockness owner.  Purple-prose proportion
and fatigue remain density owners.  A failed or incomplete call is
`INCOMPLETE`; this package never retries or silently changes provider routes.

## Aggregate result

The development result is settled `NO_GO`. Four unique static instruction
candidates were proposed; all 84 completed calls were accepted, with zero
rejections. Their train scores were 18/20, 17/20, 17/20, and 18/20. The
aggregate leaf totals were stockness 32/32, proportion 30/40, and fatigue 8/8.
No candidate met the train full-pass requirement (0/4 versus 2 required), so
selection and confirmation were not accessed.

[`public-result.json`](public-result.json) is the aggregate-only publication.
It is bound to the settled private aggregate and private result through SHA-256
commitments, without publishing candidate text or hashes, local paths, raw
prompts/responses, evidence/quotes, case labels, request/session identifiers,
or oracle/partition material. The `codex` route used `gpt-5.6-sol` at `high`;
its zero-incremental-charge status is owner-attested subscription-route
information, not independent billing proof.

Nothing is promoted: there is no prompt, rubric wording, leaf, ownership,
split, or weight change. Selection and confirmation remain closed, and the
result stays development-only.
