# Ox Alpha v4 transport pilot

This is a score-blind, outcome-blind eight-leaf transport probe. It inherits the same three public HANNA stories from the immutable v3 failure, but reduces the request to eight leaves and uses one serial cap-1 request per cell.

The exact v3 package and failed live root are verified before a v4 root can be frozen. The v3 parent launcher timed out, then its already-started bridge child later sealed the sole physical request as HTTP 524 after more than 100 seconds. It produced no accepted result and cannot be resumed.

V4 is not a scoring study. It creates no labels, scores, correlations, rankings, or prose analysis. Its outer launcher wait is 240 seconds so the bridge can finish and seal its own terminal evidence; a successful raw HTTP attempt must still finish in under 100 seconds. A permanent failure is recorded only after that normal launcher return and a stable terminal bridge-failure seal. If the outer wait expires, or terminal evidence is not yet stable, the root is explicitly uncertain and blocked rather than falsely closed. Neither state authorizes retries, escalation, paid evaluation, DSPy, or new human judging. GPT-5.6 remains the primary condition.

Prepare only after fresh zero-cost proof is available:

```powershell
python prepare_transport_successor.py --failed-v3-work-dir <immutable-v3-root> --zero-cost-proof <fresh-proof.json> --work-dir <empty-external-root>
```

The launch command is deliberately separate and must not be run until the frozen root and current runtime have been independently reviewed.
