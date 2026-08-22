# Ox Alpha v8 full supplemental scoring

This outcome-blind successor uses the exact 179-leaf Fresh88 comparison and
three public HANNA stories from v2, after independently re-verifying the
successful v7 four-leaf cap-1 transport root. It stays serial: the bridge
mutex serializes HTTP attempts, but does not prove the required cell-level
quiescence or preserve a completed-cell verification boundary for shards.

Each story has 45 four-leaf batches (44 batches of four and one of three): 135
logical requests and exactly one permitted physical attempt per request. A
failure or uncertain terminal state seals the root and authorizes no retry,
fallback, paid route, DSPy, or human route. The output retains a primary
179-leaf comparison and a clearly labeled static-178 ablation. GPT-5.6 remains
the primary condition; Ox Alpha remains provisional because max effort is not
provider-attested.

Prepare only after a fresh zero-cost proof and review of the v7 root:

```powershell
python prepare_pilot.py --fresh88-work-dir <fresh88-work> --fresh88-authority-dir <fresh88-authority> --repair1-artifacts-dir <repair1-artifacts> --zero-cost-proof <fresh-proof.json> --v7-work-dir <successful-v7-root> --work-dir <empty-private-root>
```

The separate launch command requires review of the frozen root and current
shared cap-1 runtime.
