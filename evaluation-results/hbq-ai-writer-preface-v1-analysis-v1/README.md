# HBQ AI-writer preface pilot analysis v1

Offline-only analysis of the sealed preface-pilot evidence and its separately
sealed continuation. It does not call a provider, change a rubric, choose
wording, or expose prose, prompts, raw responses, filesystem paths, or session
identifiers.

The primary result uses only terminally completed cells. The historical cell-17
failure remains missing; any continuation terminal-failure set is read from and
bound to its sealed journal and settlement rather than assumed by the analyzer.
A valid quote-only repair of cell 17 is emitted only as a separately labelled,
pre-repair-chain sensitivity result. No repair is a vote or a new replicate.

Run with caller-selected, disjoint output storage:

```powershell
python evaluation-results/hbq-ai-writer-preface-v1-analysis-v1/analyze.py `
  --original-public C:\path\to\pilot-public `
  --original-private C:\path\to\pilot-private `
  --continuation-public C:\path\to\continuation-public `
  --continuation-private C:\path\to\continuation-private `
  --output-dir C:\path\to\new-analysis-output
```

The output contains only `summary.json` and a byte-binding `manifest.json`.
It is descriptive pilot evidence, not an automatic prompt decision.

The checked-in [`results-pre-repair-chain`](results-pre-repair-chain/) snapshot
is the sealed 22-cell primary analysis before the multi-leaf cell-17 repair
chain. It keeps cells 17 and 18 missing and does not fabricate a sensitivity
score.
