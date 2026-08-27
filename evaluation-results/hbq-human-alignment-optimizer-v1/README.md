# HANNA optimizer v1

This is a provider-free development protocol, not an optimizer runtime. It prepares no request, sends no data, and cannot claim a HANNA alignment gain.

The caller supplies two local roots: the frozen Fresh88 successor contract and the pinned HANNA CSV. Their bytes must match the contract hashes before the package derives the exact 80 generated items, 39 opaque prompt groups, and group-disjoint 48/13/19 split. No user-specific source path is embedded in this package.

Six candidate prompt/profile commitments are scheduled against both the 48-item train and 13-item development partitions for each provider: 732 prospective development cells. The 76-cell candidate-versus-control confirmation geometry is a future plan only. This package intentionally rejects every selection artifact and confirmation manifest until exact per-run/provider manifest recomputation exists.

DSPy MIPROv2 and Optuna are optional offline development helpers. Neither is imported at runtime. Grok receives the same prospective schedule but remains separately reported; only the fixed Sol development endpoint selects.

The disclosure binds what this package actually prepares: opaque item/group schedule cells, provider/model destinations, and candidate hash commitments. Story/prompt bytes, profile bytes, sampler, provider request, response artifacts, and operator acknowledgement are unimplemented and must be disclosed and bound by a future executor immediately before any remote contact. Imported aggregates are always rejected until a local analyzer recomputes metrics from exact per-run evidence.

```powershell
$env:PYTHONPATH='src'
python evaluation-results/hbq-human-alignment-optimizer-v1/prepare.py --frozen-successor-contract <frozen-contract.json> --hanna-csv <hanna.csv> --output-dir <new-preflight-dir>
python evaluation-results/hbq-human-alignment-optimizer-v1/validate.py --frozen-successor-contract <frozen-contract.json> --hanna-csv <hanna.csv> --split-manifest <split.json> --execution-manifest <manifest.json> --disclosure <disclosure.json>
```

HANNA is human-reference context, not literary ground truth. A development selection is neither a production prompt nor a confirmed result.
