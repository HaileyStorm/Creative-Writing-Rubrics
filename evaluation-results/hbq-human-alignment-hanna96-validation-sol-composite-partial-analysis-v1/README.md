# Fresh96 Sol composite partial analysis

This provider-free analyzer combines two immutable Fresh96 Sol output roots. It invokes the pinned executor's Fresh96 admission and projection logic for every successful cell, including closed root and cell inventories, scheduled payload and target bindings, launch intent, receipts, raw-event/final-response associations, effective settings, command construction, and local execution identity.

The historical records contain one compatibility-only field: `codex-record.json.reported` must be exactly the observed four all-null fields. The analyzer rejects every other key/value shape, projects only that exact field away in memory, and then applies the pinned verifier. It never edits either source root.

The later root B has deterministic precedence. A fills only B non-successes, so repeated executions are never pooled or counted twice. The public result reports aggregate coverage and endpoint-specific equal-group MAE only; it omits stories, prompts, item IDs, native/local identities, and filesystem paths.

The output is a partial validation measurement: it forbids imputation, endpoint pooling, selection, confirmation, generalization, and runtime claims. One logical cell remains uncovered after the terminal ambiguity in B; no resend occurs.

```powershell
python evaluation-results/hbq-human-alignment-hanna96-validation-sol-composite-partial-analysis-v1/analyze.py --root-a C:\path\to\sol-root-a --root-b C:\path\to\sol-root-b --frozen-root C:\path\to\fresh96-freeze --result-output C:\path\to\fresh-result.json
```
