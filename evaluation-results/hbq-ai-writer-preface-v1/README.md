# AI-writer and criticism-preface protocol

This is a sealed, no-provider protocol for a question worth taking seriously: does the current AI-origin / “do not protect feelings” judge preface make HBQ more usefully exacting, merely harsher, less repeatable, or differently aligned with published HANNA labels? It contains no prose, ratings, runner, provider client, or result.

Experiment A is the primary judge test. Each frozen HANNA input is held constant across `none`, the byte-bound current prefix, and an origin-neutral strictness-only control. Each arm gets two fresh sessions. The stages are 4 input-pairs for a pilot, 12 for development, and 24 untouched holdout pairs. “Pair” means one frozen input across all three arms, not a comparison of two different stories. Each phase is evenly split between existing, verified AI-written and non-AI-written corpus items; source-model strata are balanced within those levels. Actual provenance stays internal and matched; declared provenance is a treatment. A estimates the current AI-framed preface package within each actual-origin level and its interaction, not the AI sentence alone. Published HANNA labels remain offline.

Experiment B is deliberately separate: a future Palimpsest harness runs writer identity reminder × writer “do not hold back” and sends its outputs to blind downstream grading. Experiment C is a conditional judge-side 2×2 crossover of the exact production AI-origin sentence and exact production strictness clause. It byte-reconstructs the current prefix in its present/present cell; it does not introduce a paraphrased “do not hold back” bridge. It is unavailable unless A reproduces its declared development signal and a successor freezes the exact threshold and inputs.

The study records leaf flips, scores, coverage, repeatability, confidence, criticism style, and overlap-only HANNA Kendall/Spearman. Confidence is diagnostic; it never weights the HBQ score or coverage. Batch/polarity interaction comes later, only on the 27 overlap leaves at an already validated batch size.

Run the offline checks:

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp .pytest-ai-writer-preface-v1-temp tests/test_ai_writer_preface_v1.py
.\.venv\Scripts\python.exe -m py_compile evaluation-results/hbq-ai-writer-preface-v1/study.py
```
