# L2 construct microgate execution successor

This is the unexecuted, direct-image successor for the immutable provider-free
freeze at `a711c85`. It renders the exact production singleton questions and
bundles, copies only the committed 129,853-byte stairwell PNG for `c03`, and
uses no attachment for `c04`. The expected ledger is intentionally absent from
the executor, dry run, manifests, prompts, and settlement code.

`run.py --dry-run --private-root <external-root>` creates an immutable
preexecution disclosure. Remote execution remains separately gated by an
owner's zero-incremental-charge acknowledgement; it permits exactly one
physical call per singleton and no retry or resume. Final classification must
be provided by an external boolean scorer, then is written exactly once as an
aggregate-only settlement. It cannot promote, split, merge, or reweight the
rubric.
