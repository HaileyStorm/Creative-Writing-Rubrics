# Fresh88 primary analysis v1

This is an offline, analysis-only successor for the complete Fresh88 development run. It re-verifies the exact 88 raw repair1 runs through the frozen historical runtime, reconstructs the sealed verifier matrix and development gate, and derives the six established HANNA mappings. It neither contacts a provider nor writes to any evidence input.

The frozen contract pins the analyzer and helper source bytes, the six-dimension order and mapping-set hash, the generated-only (80, excluding `Human`) and all-item (88) slices, all bootstrap seeds/draws, and both authority orders. Bootstrap remains prompt-clustered with 1,000 draws.

The public result has exactly `summary.json`, `items.jsonl`, and `manifest.json`. It contains no story or prompt prose, provider/session identifiers, run IDs, or worker identifiers. Output is written atomically and an existing output directory is always refused.

```powershell
$env:PYTHONPATH='src'
python evaluation-results/hbq-human-alignment-v3-fresh88-analysis-v1/analyze.py \
  --data-dir <restored-pinned-hanna-files> \
  --work-dir <fresh88-work> \
  --authority-dir <fresh88-freeze-v4> \
  --artifact-dir <fresh88-repair1-artifacts> \
  --historical-runtime-root <fresh88-parent-runtime> \
  --output-dir <new-empty-public-output>
```

`items.jsonl` follows the authority's canonical selection order while preserving each item's original Fresh88 execution ordinal. The output is development evidence only and must not be relabeled as confirmatory evidence.
