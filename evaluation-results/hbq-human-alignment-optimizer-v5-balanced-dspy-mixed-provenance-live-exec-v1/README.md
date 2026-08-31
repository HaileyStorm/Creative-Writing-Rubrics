# HANNA v5 Grok live executor

This versioned executor maps the evaluator's 33 logical Grok-primary cells to 30 unique outbound payloads. One descendant aliases the baseline byte-for-byte across all three groups; its three logical rows are retained as immutable lineage, but never receive roots or contacts. The executor therefore exposes ten effective candidates and permits one explicit, tool-free Grok CLI lifecycle per unique payload.

`prepare-all` performs no provider call and writes an alias manifest. `execute-one --allow-remote` is the only contact surface; it refuses aliases and existing intent, result, receipt, or response artifacts. A post-intent error is terminal `reconcile_required`; it is never retried in place. A saved Grok envelope plus one local CLI lifecycle does **not** prove native endpoint contact cardinality, so all produced receipts say `unproven`; the strict pushed v5 projector must reject them. The package's descriptive projector reports equal-group MAE only, with no selection, promotion, runtime, confirmation, or general-alignment authority. Sol remains separate.

After a current zero-charge Grok route has been independently armed, prepare a fresh root, then run distinct cell IDs in separate processes (at most ten concurrent):

```powershell
python executor.py --prepare-all --output-root C:\work\hanna-v5-live --materialization-root C:\... --frozen-successor C:\... --hanna-csv C:\... --queue-root C:\Users\Haile\.codex\state\model-work-queue --authorization-acknowledgement-sha256 <sha256>
python executor.py --execute-one --allow-remote --output-root C:\work\hanna-v5-live --cell-id <prepared-cell-id> --materialization-root C:\... --frozen-successor C:\... --hanna-csv C:\... --queue-root C:\Users\Haile\.codex\state\model-work-queue --authorization-acknowledgement-sha256 <sha256>
python executor.py --finalize-collector --output-root C:\work\hanna-v5-live --collector-output C:\work\hanna-v5-live-receipts.json --materialization-root C:\... --frozen-successor C:\... --hanna-csv C:\... --authorization-acknowledgement-sha256 <sha256>
python executor.py --descriptive-project --collector-output C:\work\hanna-v5-live-receipts.json --output-root C:\work\hanna-v5-live --materialization-root C:\... --frozen-successor C:\... --hanna-csv C:\...
```

The collector and descriptive projector are development-only evidence. They do not open confirmation, pool endpoints, select at runtime, or establish a general HANNA result by themselves.
