# HANNA optimizer v2

This provider-free successor turns a complete set of supplied train/development response receipts into independently recomputed HANNA endpoint previews. It accepts exactly the parent v1 schedule: six frozen candidates, 61 train/development items, and two distinct providers (732 cells). It accepts no aggregate scores and no confirmation material.

For each candidate and provider it first averages predicted and human values within each of the seven development prompt groups, then computes tie-aware Spearman across those seven equally weighted group means for each HANNA dimension. Macro Spearman equally averages the six dimension coefficients; MAE equally averages the 42 prompt-group-by-dimension errors. Only the Sol development endpoint produces a deterministic selection preview, using macro Spearman descending, then group-weighted MAE ascending, then candidate ID. Grok remains a separate descriptive screen; provider values are never pooled. All six dimension correlations must be defined for every reported development endpoint. Train cells are validated for complete supplied-receipt geometry but do not create a second endpoint.

The 19-item/eight-group confirmation split remains unopened and structurally absent from the accepted evidence. DSPy and Optuna remain optional development-time candidate tools from the parent protocol; neither is imported, required, or granted runtime selection authority here.

Input is one canonical JSON object with exact keys `format_version`, `study_id`, `kind`, `execution_freeze_sha256`, and `cells`. Each of the 732 cells has only `cell_id`, `task_payload_sha256`, base64-encoded exact response bytes, and a receipt claim. The receipt binds the frozen request hash, exact response-byte hash, provider, model, transport, claimed successful one-contact status, and native response/request/session identity. An integration must inject a binding verifier for every receipt; the command-line entrypoint deliberately has no such injection surface. Response swapping, duplicate contact identities, and caller aggregates are rejected.

The binding verifier and root labels are not cryptographically pinned external trust. Therefore the output status is explicitly non-empirical, and the computed candidate is a selection preview with no confirmation, empirical, or production authority. A later versioned successor must pin and verify an external trust root before these computations can support an empirical selection claim.

Sol native bytes must report the exact requested model and a unique response identifier, then contain the structured response in native message content. Grok native bytes must report one normal turn, the exact approved build model, unique request/session identifiers, and the structured response. Exact native bytes are hashed before JSON parsing; the output separately reports requested, native-reported, and supplied-receipt-bound identity labels. It is aggregate-only and atomically published without overwrite.

The parent v1 OpenAI chat adapter records a configured Sol reasoning effort but does not transmit or natively attest it. The Grok CLI adapter requests its configured effort, but the accepted native envelope does not attest it. V2 reports those limitations explicitly rather than treating configuration as native proof.

An integration calls `analyze(..., receipt_binding_verifier=...)`. Direct CLI execution fails closed because it has no binding-verifier injection surface.

This is a non-empirical development selection preview, not a confirmed alignment improvement or production prompt.
