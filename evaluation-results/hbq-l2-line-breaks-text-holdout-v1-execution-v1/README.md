# L2 text-only line-break holdout executor v1

This sibling executor is the only remote-capable surface for the frozen public
synthetic text-only holdout.  It binds the exact 1290b6e freeze, its declared
runtime and decision lineage, and the canonical quote-normalization policy
before importing the frozen planner or production runtime.

It schedules 24 singleton text calls: four poem fixtures, the candidate
line-break question and unchanged necessity control, three repetitions each.
There are no image files, image flags, attachments, or text-as-image
substitutions.  Execution is claim-first and one-shot; a contact failure blocks
later slots and yields no result.  All four schema-valid verdict states are
accepted by transport; an external private boolean scorer alone decides match
bits after all 24 accepted calls.

All eight cells must be 3/3 for `HOLDOUT_ELIGIBLE_ON_SUCCESS`; a completed
miss is `NO_GO`; incomplete or ambiguous execution has no result.  Settlement
is claim-bound and aggregate-only.  This executor promotes nothing.
