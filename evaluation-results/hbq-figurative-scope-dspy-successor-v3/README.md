# Figurative scope DSPy successor v3

This provider-free, development-only settlement preserves v2 as incomplete.
It binds the public v2 freeze commit and the finalized private reconstruction
and settlement hashes. One fully
reconstructed accepted TRAIN mismatch makes the two-candidate, every-affected-
cell gate impossible: each candidate must pass all six affected leaf-cells,
with three successful repetitions per cell. The resulting outcome is `NO_GO` with
zero new provider calls; selection and confirmation remain closed.

The typed-evidence checks are a regression for the production representation:
exact-only, summary-only, and mixed evidence are valid when well-formed; exact
quotes must ground in supplied source; malformed evidence is invalid. They do
not reinterpret or relabel the imported historical result.

No candidate or synthetic text, case labels, private paths, prompts, raw
responses, evidence, session identifiers, selection content, or confirmation
content is published here. This does not promote a prompt, rubric, leaf,
ownership rule, split, or weight.

`public-result.json` is the settled aggregate-only `NO_GO` projection with the
pinned v2 and v3 private aggregate/result lineage. `run.py --dry-run` and
`run.py --settle --private-root ...` are permanently provider-free: settlement
only verifies the pinned private engine/freeze inputs and emits that projection.
There is no provider-execution mode.
