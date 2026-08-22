# Ox Alpha transport successor v3

This is a score-blind, 16-leaf transport successor bound to the immutable failed v2 root. It uses the shared cap-1 route: exactly one physical attempt per logical request.

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe evaluation-results\hbq-human-alignment-supplemental-providers-ox-alpha-v3\prepare_transport_successor.py --failed-v2-work-dir <failed-v2-root> --zero-cost-proof <fresh-proof.json> --work-dir <fresh-v3-root>
.\.venv\Scripts\python.exe evaluation-results\hbq-human-alignment-supplemental-providers-ox-alpha-v3\run_transport_pilot.py --work-dir <fresh-v3-root>
.\.venv\Scripts\python.exe evaluation-results\hbq-human-alignment-supplemental-providers-ox-alpha-v3\verify_transport_pilot.py --work-dir <fresh-v3-root>
```

Launch still requires a current zero-cost proof. The protocol has no score, label, correlation, or promotion surface.

Historical outcome: the parent launcher timed out before its bridge child returned. The already-started child later recorded the sole cap-1 physical request as HTTP 524 after 127.808 seconds. No result was accepted; the root is permanently closed and must not be resumed.
