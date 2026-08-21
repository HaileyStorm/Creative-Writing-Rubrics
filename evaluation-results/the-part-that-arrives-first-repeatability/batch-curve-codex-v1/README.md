# Codex batch-curve successor

This is the concrete, local-first Codex CLI successor to the frozen v2 batch
protocol and the callback-only live-v1 mechanism. It contains no result.

`plan` and `prepare --dry-run` perform only local checks. `execute` reprobes the
sealed Git/Codex environment, then uses the frozen v2 question order and exact
strict-AI prompt for every physical Codex call. The ordered runner writes v4
accepted/rejected evidence and the local verifier replays prompts, verdicts,
feedback, score descendants, and session provenance with zero contexts.

Raw provider evidence stays in an operator-selected private evidence root. The
public work directory contains only relative path/byte/hash commitments to it.
No live evidence is currently packaged, and the result remains non-publishable
until its separate analysis gate is completed.

Screening never makes a size recommendation. In particular, it cannot recommend
a size above 24 unless separate deep HANNA evidence validates the exact stack.
