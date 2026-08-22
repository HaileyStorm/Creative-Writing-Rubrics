# Batch-curve Codex remainder v2

This executable successor consumes exactly the 47 unfinished scored batch
partitions sealed by remainder v1. It never resumes the stopped parent in
place, never repeats cell 36 batches 1–31, and gives each scored unit one
physical Codex attempt. A durable but incomplete attempt is uncertain and
halts instead of being resent.

`prepare` is offline and refuses any dirty, untracked, uncommitted, or
unpushed recovery source. Each of six planned eight-unit epochs starts with a
minimal native Codex model preflight against the pinned model. Those preflight
calls are separate from, and never scored as, the 47 batch calls. If a
15-minute proof expires, the next invocation appends a replacement preflight
for that epoch before resuming. `execute` checks the clock before every scored
call and stops before contact if no current proof exists. Raw output stays in
an external private root; the public root stores commitments only.

Every preflight attempt, including a failed or malformed response, is retained
as a separate terminal provider-call record. These calls are reported apart
from the fixed 47 scored calls.

This produces recovery evidence, not a batch-size recommendation. Analysis
remains non-live and a recommendation stays disabled.
