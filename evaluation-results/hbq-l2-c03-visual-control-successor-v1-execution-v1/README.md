# L2 C03 visual-control successor v1 — execution v1

This is the execution-only successor for the frozen public-synthetic C03 visual
control package. It schedules twelve isolated image-backed calls: two frozen
visual leaves × two fixtures × three repeats. Provider-facing prompts never
include the expected ledger.

It reuses the committed L2 construct v2 executor lifecycle: one physical
attempt per slot, a pre-contact claim, terminal sidecars, bounded local command
diagnostics, canonical production quote normalization, and claim-bound,
aggregate-only settlement. Before any import that can reach the production
runner, it verifies the C03 freeze, executor dependency, and current runtime
bytes against commit `15f30863eee60619382c4b87fd3a13dd778ec50d`.

`run.py --dry-run --private-root <outside-checkout-root>` writes a provider-free
prepared root and exact disclosure. `--execute` additionally requires both
explicit remote and zero-incremental-charge flags; this package does not call a
provider during validation.

All four cells must be 3/3 correct for `FIXTURE_DIAGNOSIS_SUPPORTED`. Any
complete-cell miss is `NO_GO`; incomplete or ambiguous execution produces no
result. Neither outcome promotes a prompt, rubric, leaf, ownership, split,
merge, or weight. The expected ledger is opened only by an external boolean
scorer after all responses are terminally accepted; the package publishes
aggregate-only output.
