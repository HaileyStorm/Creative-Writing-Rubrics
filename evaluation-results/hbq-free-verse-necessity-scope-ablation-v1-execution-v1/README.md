# Free-verse necessity / scope ablation executor freeze

This is the zero-call execution successor for the independently reviewed
`hbq-free-verse-necessity-scope-ablation-v1` freeze. It binds the predecessor's
exact reviewed bytes and renders 36 public-synthetic, one-leaf singleton
prompts for the exact Codex route: `gpt-5.6-sol` at `high` reasoning.

This package has no provider transport or execution command. Its local
prepare/claim/terminal/settlement machinery exists to freeze the future
one-attempt lifecycle: claim before any contact, no retry or resume after a
claim, schema-plus-exact-evidence validation, immutable terminal records, and
an immutable aggregate-only settlement. A future authorized contact runner
must use this contract; this package itself makes zero provider calls.

No automatic prompt, rubric, ownership, split, merge, or weight promotion is
authorized. Run `python run.py --verify`, or `python run.py --prepare
--private-root <external-empty-directory>` to create public-synthetic local
dry artifacts only.
