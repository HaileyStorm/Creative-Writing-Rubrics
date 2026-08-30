# HANNA balanced development-only optimizer

This successor accepts a projection only when it is byte-identical to a fresh replay by the pinned balanced-training verifier over the supplied collector evidence, frozen successor, and HANNA CSV. It independently recomputes the five candidate endpoints over the retained balanced subset: Grok over four items/four prompt groups and the sprinkled Sol endpoint over two/two. The whole five-candidate Grok group containing immutable, no-resend terminal `v4-cell-327fe788866eb61b` is excluded. Real Optuna 4.9.0 `GridSampler` minimizes `0.8 × Grok mean absolute error + 0.2 × Sol mean absolute error`, with additive lower-Grok-coverage (`1e-6`) and request-byte (`1e-12`) penalties. Per-dimension Spearman values, including nulls, remain descriptive diagnostics and never get imputed.

The reviewed 30-cell balanced result selects the existing `candidate-52d1be4bc34e0018` baseline: objective `1.5722222267539725`, Grok MAE `1.638888888888889`, sprinkled-Sol MAE `1.3055555555555556`, and Grok coverage `1.0`. Coverage and the finding that no current candidate improved apply only to the retained subset. This is a development result only: confirmation is unopened; Grok reasoning is unattested; and the Sol observations establish local lifecycle, not native endpoint-contact cardinality. The aggregate-only [public result](public-result.json) pins the optimizer, contract, result, balanced projection, and excluded-terminal commitments without exposing stories or local paths.

`prepare_dspy_descendant_inputs()` instantiates the real DSPy 3.3.1 `Predict` shape but only returns its exact canonical inputs with `provider_calls_made: 0`. A separate governed executor must own any model invocation; this package has no DSPy forward/dispatch path.

Provider-free downstream call:

```powershell
$result = $optimizer.optimize_balanced_projection(balanced_projection_path=$projectionPath, balanced_collection_evidence_path=$collectionPath, frozen_successor_path=$frozenPath, hanna_csv_path=$hannaPath)
$diagnostics = $optimizer.training_diagnostics(balanced_projection_path=$projectionPath, balanced_collection_evidence_path=$collectionPath, frozen_successor_path=$frozenPath, hanna_csv_path=$hannaPath)
```

The projection must exactly equal `verify_balanced_training_receipts(...)` at the time of use; this package performs that replay before accepting it and sends no provider requests.
