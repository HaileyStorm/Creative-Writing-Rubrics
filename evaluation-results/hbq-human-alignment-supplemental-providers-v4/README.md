# Supplemental HANNA Nous compatibility successor v4

v4 is provider-free. It validates the immutable failed v2 batch-16 evidence and reconstructs its v1 input lineage with static JSON, fingerprints, and the frozen seed only; it never imports v1/v2/v3 runtime helpers. A fresh v4 freeze additionally fingerprints the current runner, launcher, and bridge.

The recorded future pilot policy remains three sequential batch-8 cells, one worker and one physical attempt per logical request, 600-second timeout, 2xx-only, zero recovery, distinct sessions, exact raw transport verification, and each success below 100 seconds. This compatibility snapshot carries historical 16-question cells only; it is not an execution-ready batch-8 schedule. v4 creates no execution surface and makes zero provider calls. A later runner must separately freeze an exact 8-question schedule, per-cell disclosure, current zero-charge route evidence, and native runner/request bindings. Existing—including empty—roots are rejected, so it cannot adopt an orphan or resend a predecessor attempt.

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe evaluation-results\hbq-human-alignment-supplemental-providers-v4\prepare_transport_successor.py --failed-v2-work-dir <immutable-v2-root> --work-dir <fresh-v4-root>
```
