# Four-state polarity and confidence diagnostic v1

This compact offline successor reads four pinned, tracked public aggregate
artifacts. It does not request model work or accept an invented replacement for
the archived evidence.

The polarity source reports 81 paired comparisons and eight disagreements, but
not the full four-state cross-tab. Accordingly, this package publishes and tests
the complete reducer policy without presenting fabricated cell counts. The
confidence source already reports an equal-budget result: reallocating calls by
low initial confidence was worse than uniform allocation on its repeat-consensus
proxy. That negative result is retained as a descriptive, noncanonical NO-GO.

`summary.json` and `manifest.json` bind this successor to those source artifacts.
Run offline:

```powershell
python evaluation-results/hbq-four-state-polarity-confidence-v1/analyze.py --output-dir results
python evaluation-results/hbq-four-state-polarity-confidence-v1/verify_output.py --output-dir results
```
