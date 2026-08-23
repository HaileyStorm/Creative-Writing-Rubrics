# Premise-scale ownership: aggregate result v1

This is the aggregate-only public result for the completed premise-scale
ownership screen. It publishes no fixture text, fixture aliases, expected
labels, individual cell or slot outcomes, prompts, model outputs, private
evidence, paths, or provider/session/request/run identifiers. The
machine-readable result is
[premise-scale-ownership-public-aggregate.v1.json](premise-scale-ownership-public-aggregate.v1.json).

## Result

All 72 of 72 singleton slots completed and were accepted on their first
attempt. The fixed diagnostic used twelve synthetic artifacts, two selected
leaves, and three repetitions per cell.

The settled decision is **DIAGNOSTIC_FAIL**. Nine of 20 scored cells passed.
There were 37/72 overall raw matches. This result is a diagnostic screen, not a
general claim or a causal explanation. It does not identify fixtures, cells,
slot outcomes, or their expected states.

## What this supports—and does not

No promotion follows from this result. It authorizes no prompt, rubric, leaf,
ownership, split, or weight change. The sealed private settlement remains the
receipt-level verification authority. This public package binds the source
settlement, execution commitments, and CWR lineage through opaque SHA-256 and
Git commitments without copying private material.

## Local verification

From the repository root, run:

```powershell
python evaluation-results/hbq-premise-scale-ownership-v1-result-v1/verify_output.py
```

The verifier checks fixed aggregate semantics and arithmetic, source
commitments, the three-file allowlist, and forbidden private or per-case
content.
