# Sol local-lifecycle admission manifest

This provider-free package authenticates the 33 original successful Sol exec-v3 lifecycle admissions through the pinned admission verifier. Its public result carries only cell IDs, artifact commitments, and the explicit local-lifecycle ceiling; it excludes the two immutable original terminals and every replacement descendant.

Generate only after the proof directory contains all 33 immutable admission proofs:

```powershell
$env:PYTHONPATH='src'
python evaluation-results/hbq-human-alignment-optimizer-v4-sol-local-lifecycle-manifest-v1/generate.py --proof-root C:\Users\Haile\Documents\cwr-hanna-v4-sol-local-lifecycle-admissions-e5c50b1\proofs --frozen-successor-path C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json --hanna-csv-path C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv --result-path evaluation-results/hbq-human-alignment-optimizer-v4-sol-local-lifecycle-manifest-v1/result.json
```

The result is descriptive provenance, not native-contact proof or a model-quality, selection, or generalization result.
