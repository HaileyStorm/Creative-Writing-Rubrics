# Multisample successor

This package finishes the remaining 254 cells of the sealed multi-sample repeatability schedule. It first verifies the complete 801-file predecessor manifest, the unchanged 330-row plan, its contiguous 76 accepted completions, 146 unique historical sessions, five rejection records, and the nine-file sequence-77 failure directory.

The predecessor is read-only. Sequence 77 is run anew; its three failed predecessor attempts are lineage, never an accepted result. New output lives in a separate external work directory. The successor preserves raw structured responses. It may project an evidence quote only by removing one matching outer `“…”` pair when its interior is already an exact source substring; every projection has a deterministic audit.

Dry-run verifies and seals the successor journal without contacting a provider:

```powershell
$env:PYTHONPATH='src'
python evaluation-results/hbq-multisample-repeatability-v1-successor-v1/run_successor.py <predecessor-root> <successor-work> --dry-run
```

Omit `--dry-run` only after reviewing the external destination: it uses the existing Codex CLI route, does not use a paid API, and does not collect human judgment. The successor does not copy predecessor sources or outputs into the repository.

The live command additionally requires `--allow-remote`.
