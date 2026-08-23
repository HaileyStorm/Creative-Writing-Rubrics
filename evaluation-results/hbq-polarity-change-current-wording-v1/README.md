# P1 polarity-change current-wording v1

This public, synthetic, provider-free development freeze screens the eleven
P1 surface-polarity findings identified by the structural audit. It tests the
current production wording only: there is no rewrite arm, no rubric change,
and no execution authorization.

Each leaf has four concise, leaf-specific fixtures: a clearly satisfied case,
a clearly failed case, an inapplicable task case, and a relevant case with the
necessary evidence withheld. Every fixture is rendered as a singleton prompt
three times, for 132 prospective calls. Expected labels live only in the local
ledger and are excluded from provider-facing prompts.

`run.py` has only `--dry-run` and `--render-plan` modes. It binds the current
judge prompt, response schema, runner, question-index records, and the eleven
source modules. No prompt, rubric, leaf, ownership, split, or weight promotion
is authorized by this package.
