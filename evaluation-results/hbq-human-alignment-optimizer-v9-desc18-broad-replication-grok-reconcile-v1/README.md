# Desc18 Grok reconciliation v1

This provider-free successor recovers the 64 already-returned desc18 Grok envelopes without modifying or resending the immutable source run. The source executor rejected each valid response only because its added quality validator required canonical JSON bytes while Grok persisted semantically valid pretty-printed native envelopes.

The reconciler rechecks the exact frozen schedule, source executor Git blobs, prepared disclosure/acknowledgement/route/payload/schema bytes, launch intent, terminal result, response inventory, prompt bytes, native identity uniqueness, `text == structuredOutput`, and six-dimensional response quality. It reconstructs the request, identity, and settings and passes them through the pinned native runner validator. The resulting collector retains each raw envelope and its SHA-256 hash. Its distinct reconciliation study ID, kind, and exact source-lineage object prevent it from being mistaken for a collector emitted by the failed direct executor.

This is reconciliation, not execution: it makes zero provider calls and launches zero processes. The historical wave launched 64 processes, but native endpoint-contact cardinality remains unproven. Confirmation remains unopened and the collector has no selection, promotion, runtime, or cross-endpoint authority.

Example:

```powershell
python reconcile.py --output-root C:\Users\Haile\Documents\cwr-desc18-broad-grok-4d3b2ef-20260901a --freeze-root C:\Users\Haile\Documents\cwr-hanna-desc18-open-freeze-83d7be7-20260901a --collector-output C:\Users\Haile\Documents\cwr-desc18-broad-grok-4d3b2ef-20260901a.reconciled-v1.collector.json
```
