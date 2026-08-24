# L2 text-only line-break holdout v1

This is a fresh, public-synthetic, text-only holdout for the development-only
candidate wording of `form.poetry.free_verse.line_breaks`. It retains the
canonical `form.poetry.free_verse.necessity` question as its unchanged control.
It changes no registry text, rubric, leaf ownership, split/merge state, or
weight.

The four poem-scope artifacts are newly written for this holdout. They cover
controlled lineation, administratively wrapped prose, no line breaks, and
locally controlled but form-nonessential lineation. They produce eight cells
and 24 planned singleton slots: two leaves per case and three repeats. The
expected ledger is separate from all rendered prompts.

This package excludes images on purpose. The corrected C03 visual-control
diagnostic result found the visual controls non-diagnostic for the
candidate-wording question, so it remains decision lineage rather than being
reused as a fixture. The v2 source package remains the design and wording
predecessor.

This is a provider-free freeze: it authorizes zero provider calls and exposes
only `--dry-run` and `--render-plan`. Both commands use the canonical production
renderer; neither command can execute, retry, resume, settle, or promote a
result.
