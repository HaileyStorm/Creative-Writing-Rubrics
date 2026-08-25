# S2 fresh disjoint confirmation v2

This provider-free package freezes the newly approved wording-only confirmation
for `scope.passage.status`. It retains the candidate wording exactly and uses
three new carrier/evaluation records with no identity, prose, record-template,
or answer-key-language reuse from the prior holdout, semantic pilot, or consumed
v1 confirmation. The strict schema requires `completion_status`, so the task
contract uses the neutral value `unknown` and requires evidence from the
supplied carrier or context, never framing metadata.

The current freeze also binds a prior-root freshness audit. Its missing-review
case declares fragment status inside the supplied context while leaving the
evaluator response absent; applicability therefore does not depend on task
metadata.

The candidate-only geometry is three fixtures by two repeats: six Sol/high
singleton calls. The sealed answer key distinguishes a visible full-work bar,
a complete bounded evaluation that applies no such bar, and an excerpt packet
with no evaluator response. Answer-key content is never loaded while prompts
are prepared or rendered.

Every accepted result must be the first raw response, with zero rejected retry
and zero normalization. Live execution also requires the checkout HEAD to be
exactly `6ae9ee0db17dda61bb9adc00a60bcd8072969d5d` before the claim is created.
A 6/6 result opens independent wording-only promotion review; nothing changes
automatically.

Provider-free preparation:

```powershell
.\.venv\Scripts\python.exe evaluation-results/hbq-nonpoetry-scope-disjoint-confirmation-v2/run.py `
  --private-root <PRIVATE_ROOT> `
  --dry-run
```

The sole future live command, from the exact frozen CWR checkout:

```powershell
.\.venv\Scripts\python.exe evaluation-results/hbq-nonpoetry-scope-disjoint-confirmation-v2/run.py `
  --private-root <PRIVATE_ROOT> `
  --execute --allow-remote --acknowledge-zero-incremental-charge
```
