# Ox Alpha v9 unit-retry successor

V8’s sealed 524 failure is immutable lineage, not a result to resume. V9 freezes
the same 135 four-leaf (final three-leaf) units and executes one cap-1 run per
unit attempt. A retry is permitted only for an offline-verified sealed, quiescent
single HTTP 524 with no inbound message, result sidecar, checkpoint, verdict, or
score; it resends the same prompt and schema without error feedback. Other
outcomes quarantine the unit. Each resumed pass receives a new epoch ID while
retaining the protocol round and frozen cursor. Scores are complete-case only:
45 accepted batches per story, then all three stories for their mean.

## Offline orphan recovery

Use this only after an interrupted executor left one dangling intent and its
`execution-claim.json`, and only after confirming the claiming process is no
longer running:

```powershell
.venv\Scripts\python.exe evaluation-results\hbq-human-alignment-supplemental-providers-ox-alpha-v9\run_pilot.py --work-dir <private-work-root> --adjudicate-orphan
```

The command makes no provider call. It validates the claim and sealed attempt
evidence, records immutable recovery authority, updates state, then removes the
claim. If contact evidence is uncertain, it stops without retrying or removing
the claim.

An immutable `*-global-stop.json` is different: it records a charge signal or
HTTP 402 and blocks all execution. Do not use orphan adjudication to bypass it;
the study remains fail-closed.
