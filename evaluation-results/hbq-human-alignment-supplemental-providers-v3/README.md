# Supplemental HANNA Nous transport successor v3

This score-blind batch-8 pilot is the sole preregistered successor to the failed v2 batch-16 root. It binds that failure's frozen contract, exclusive claim, invocation, journal, and rejected raw attempt. It sends three distinct Flash cells sequentially, once each. Any failure closes v3 permanently.

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe evaluation-results\hbq-human-alignment-supplemental-providers-v3\prepare_transport_successor.py --failed-v2-work-dir <failed-v2-root> --work-dir <new-v3-work>
.\.venv\Scripts\python.exe evaluation-results\hbq-human-alignment-supplemental-providers-v3\run_transport_pilot.py --work-dir <new-v3-work> --timeout 600
.\.venv\Scripts\python.exe evaluation-results\hbq-human-alignment-supplemental-providers-v3\verify_transport_pilot.py --work-dir <new-v3-work>
```

Only a verified 3/3 pilot enables batch-8 development. It remains explicitly unmatched to primary batch-32 and v2 batch-16. No new human judgment, paid evaluation, Pro escalation, DSPy route, retry, or further automatic batch-size step is authorized.
