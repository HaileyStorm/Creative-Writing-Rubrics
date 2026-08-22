# HBQ confidence diagnostics

This offline-only analyzer turns pre-sanitized, sealed response metadata into aggregate confidence diagnostics. It never contacts a provider, changes HBQ scores or coverage, or treats confidence as a truth signal.

The caller supplies one or both external evidence directories. Each contains exactly `confidence-input.json` and a `manifest.json` whose `files` map commits the input bytes. Inputs contain only complete model fingerprints, manifest bindings, stable opaque IDs, numeric HANNA ratings, roles, weights, verdict labels, and confidences. They must not contain prose, prompts, evidence text, request IDs, sessions, or provider responses.

```powershell
python evaluation-results/hbq-confidence-diagnostics-v1/analyze.py `
  --repeat-evidence-dir <sealed-repeat-input> `
  --fresh88-evidence-dir <sealed-88-input> `
  --output-dir <new-empty-output-dir>
```

To make the sealed inputs from the known private evidence roots, use the adapters rather than hand authoring a payload:

```powershell
python evaluation-results/hbq-confidence-diagnostics-v1/prepare_fresh88_input.py --help
python evaluation-results/hbq-confidence-diagnostics-v1/prepare_repeat_input.py --help
```

The Fresh88/Grok adapter binds the Fresh88 primary summary/items/manifest, exact 80-generated/88-total selection, private run configuration fingerprints, and the completed Grok verifier manifest before emitting a prose-free input. The repeat adapter accepts only the authoritative complete 11-story, five-repeat frozen HBQ work root.

`repeatability_confidence_evidence` measures stable versus flipping leaves plus Brier/ECE and reliability bins against a **leave-one-repeat-out** unique modal verdict. Tied leave-out consensus labels are excluded before those metrics. The leave-out verdict is only an empirical same-input proxy, never human truth. It reports role-stratified YES-rate and effective-confidence-mass diagnostics rather than invented confidence-weighted HBQ scores or coverage. Where every leaf has at least two responses, it also reports a fixed-total-budget bootstrap of observed repeats: uniform one-extra-sample-per-leaf versus low-initial-confidence allocation. Tied simulated decisions abstain. This is a within-observed-responses simulation, not evidence that new calls would behave identically.

`fresh88_confidence_evidence` reports separate per-fingerprint 80-generated primary and all-88 secondary aggregates. For every HANNA dimension it uses the frozen mapped HBQ score and mapped effective confidence mass, then reports rank-based confidence/HANNA agreement and error associations. They are descriptive associations; HANNA is not converted into binary leaf truth, so the analyzer deliberately does **not** emit Brier, ECE, or reliability claims for those records.

Published output is aggregate-only (`summary.json` and `manifest.json`). It contains no item IDs, prose, prompts, raw verdicts, sessions, request IDs, or provider response text. Verify it independently with `python evaluation-results/hbq-confidence-diagnostics-v1/verify_output.py --output-dir <output>`. Confidence is diagnostic and cannot become canonical scoring, coverage, a promotion gate, or an automatic repeat policy from this analysis alone.
