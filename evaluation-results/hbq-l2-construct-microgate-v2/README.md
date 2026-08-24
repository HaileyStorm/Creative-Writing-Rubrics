# L2 construct microgate v2

This frozen, public-synthetic successor tests one development-only candidate
wording for `form.poetry.free_verse.line_breaks`. It does not change the
registry, ownership, aggregate influence, leaf count, split/merge state, or
weight. `form.poetry.free_verse.necessity` remains canonical.

The predecessor package and its expected ledger are pinned as immutable
historical provenance. The `608025b` repair-era v2 execution accepted six
slots, then produced a schema-valid `NOT_APPLICABLE` response for slot 7 that
its local three-state enum rejected; its later 17 slots were blocked. It is a
non-voting diagnostic: it supplied no rubric result, aggregate, or settlement.

Four poem-scope cases isolate controlled lineation, arbitrary prose wrapping,
the absence of line breaks, and minimal lineation. Two visual controls are carried forward unchanged from v1 by pinned
reuse: the impossible-stairwell image and the missing-image boundary. The
six artifacts have two owning leaves each and three singleton repeats, for
36 planned later-executor calls and 12 ledger cells.

Expected states are confined to `expected-ledger.json`; provider-facing prompt
generation receives no case ID, expected state, or ledger metadata. This
package has no execution surface and makes no provider calls. Run
`python run.py --dry-run` or `python run.py --render-plan` for offline checks.
