# L2 v2 construct microgate execution

This fresh 36-slot executor consumes the committed provider-free L2 v2 package
at `484134b`. It evaluates the candidate line-break wording and the unchanged
necessity/visual controls without loading its expected ledger. The six-case,
12-cell schedule is strictly singleton and includes four response states.

The failed older root is retained as explicit non-voting lineage: six accepted
responses, then a schema-valid `NOT_APPLICABLE` response rejected by the old
three-state local enum, followed by 17 blocks. It has no result, aggregate, or
settlement and is never resumed or retried.

`run.py --dry-run --private-root <external-root>` writes only provider-free
artifacts. Remote execution requires both explicit flags, one physical dispatch
per slot, a fresh root, subscription authentication, and no API credential
environment. Every requested response parent exists before dispatch; bounded
private stdout/stderr and receipt/terminal hashes make failures inspectable.

Settlement requires an external boolean scorer and publishes aggregate counts
only through a claim-bound prepared transaction and commit marker. The four
candidate line-break cells are the target; the four necessity and four visual
cells are controls. Only twelve 3/3 cells make the candidate holdout-eligible;
any target or control miss is NO-GO. Public output reports target/control
counts without labels. No execution result promotes, splits, merges, reweights,
or otherwise edits the rubric.
