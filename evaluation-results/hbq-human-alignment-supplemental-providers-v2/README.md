# Supplemental HANNA Nous transport successor v2

This is a pre-execution, score-blind transport successor after the v1 Flash route failed at its batch-32 transport boundary. It binds the v1 contract, source helpers, runner, selected external inputs, and current canonical Nous bridge/launcher bytes. v1 evidence is preserved; GPT-5.6 Sol remains the primary study.

Prepare a new external work directory from a valid v1 work freeze, then run the pilot:

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe evaluation-results\hbq-human-alignment-supplemental-providers-v2\prepare_transport_successor.py --parent-work-dir <v1-work> --work-dir <new-v2-work>
.\.venv\Scripts\python.exe evaluation-results\hbq-human-alignment-supplemental-providers-v2\run_transport_pilot.py --work-dir <new-v2-work> --timeout 600
.\.venv\Scripts\python.exe evaluation-results\hbq-human-alignment-supplemental-providers-v2\verify_transport_pilot.py --work-dir <new-v2-work>
```

The pilot makes exactly three independent 16-question Flash calls, one at a time, with one logical request per cell. An exclusive work-root claim is written before the first send. It binds the raw bridge result/request, sealed evidence receipt, serialization proof, HTTP status/timing ledger, and bridge run ID directly; it does not infer those facts from a checkpoint. The pilot does not read or publish score files, HANNA ratings, correlations, or prose-derived results. Every successful cell must be replayable, unrecovered, and finish in under 100 seconds. A failure, retry, invalid completion, duplicate evidence receipt, or boundary-duration result permanently closes v2 for that work root: preserve it and preregister batch-8 v3 instead of retrying or mutating this protocol.

Only a verified 3/3 pilot can create `development-enablement.json` and permit the full batch-16 development runner. Any resulting comparison is explicitly **unmatched to primary batch-32** unless separately frozen paired Sol batch-16 cells exist. The transport failure does not promote Nous Pro, and this successor does not use DSPy.

Remote disclosure remains the runner's per-cell disclosure. No new human judging occurs, and no paid route is introduced.
