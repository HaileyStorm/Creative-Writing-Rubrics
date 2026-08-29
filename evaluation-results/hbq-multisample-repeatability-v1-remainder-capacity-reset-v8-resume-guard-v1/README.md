# V8 resume guard v1

Status: `CONTROL_GUARD_ONLY`.

This is a provider-free controller around the immutable V8 executor, not a V8 replacement and not a scientific result. It exclusively creates a separate guard root, binds an explicitly supplied V8 runtime root, its fixed `executor.py` relative path, exact SHA-256, exact V8 study ID, and the prepared external work-root identity, then appends a guarded intent/completion record for a future sequence.

Before an injected delegate can run, it reuses V8's prepared, accepted, and session validators; independently counts physical session-bearing contacts; requires equality with V8's `provider-contacts` journal rows; rejects unresolved intent/pause before V8's potentially recovery-writing accepted-state path, orphan output, drift, reparses, and any previously uncompleted guard intent. An exclusive per-sequence claim is created before delegation and retained as immutable evidence. A delegate return is accepted only after a second read-only V8 validation proves the exact sequence settled with exact contact topology. The API has no provider implementation and is disabled unless a caller explicitly supplies and permits a delegate.

For the existing separate V8 runtime, pass its root explicitly; this does not copy or modify that runtime:

```powershell
$runtime = 'C:\Users\Haile\Documents\Creative-Writing-Rubrics-v8-runtime-e50dd50\evaluation-results\hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v8'
# guard.prepare_guard(..., v8_runtime_root=Path($runtime))
```
