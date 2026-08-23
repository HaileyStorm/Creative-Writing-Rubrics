# Final manual settlement successor

This provider-free successor validates the committed `ac216eb` execution at an
explicit external private root. It preserves the original immutable
`INCOMPLETE` settlement, verifies the exact runtime-schedule digest, all 24
format-5 terminal-sidecar first-attempt Sol/high checkpoints, regenerated
bundle/question commitments, and checkpoint-to-rendered prompt bytes.

It writes only immutable aggregate outputs in this package. It makes no
provider calls, does not rerun the executor, and grants no promotion authority.
