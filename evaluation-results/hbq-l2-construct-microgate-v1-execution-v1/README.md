# L2 construct microgate execution successor, v2

This is the fresh, direct-image v2 successor for the immutable provider-free
freeze at `a711c85`. Its immediate v1 ancestor at `2fb18cb` made one claimed
slot-1 dispatch which returned zero without writing its requested response;
that is an ambiguous transport outcome, not a rubric result or a vote. Its
claim, receipt, terminal sidecar, and the 23 blocked later slots remain
immutable. V2 uses a new study and slot namespace and requires a new private
root; it never resumes or retries v1.

It renders the exact production singleton questions and bundles, copies only
the committed 129,853-byte stairwell PNG for `c03`, and uses no attachment for
`c04`. The expected ledger is intentionally absent from the executor, dry run,
manifests, prompts, and settlement code.

`run.py --dry-run --private-root <external-root>` creates an immutable
preexecution disclosure. Remote execution remains separately gated by an
owner's zero-incremental-charge acknowledgement; it permits exactly one
physical call per singleton and no retry or resume. Before scanning any prior
attempt state or starting a provider-capable process, execution creates an
exclusive immutable claim; a stale claim or attempt is retained and fails
closed rather than being retried.

Before each Codex dispatch, the executor creates the requested response
directory. Each private receipt retains bounded local stdout/stderr diagnostics
and exact byte/hash counts, so a zero-return missing-output failure is
inspectable without becoming a public result.

Final classification must be provided by an external boolean scorer. The
private settlement and aggregate-only public result are hash-bound to the
execution claim and written through a prepared publication transaction whose
commit marker is the sole completed-publication authority. It cannot promote,
split, merge, or reweight the rubric.
