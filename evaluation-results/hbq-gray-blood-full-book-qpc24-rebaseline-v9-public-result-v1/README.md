# QPC24 V9 full-book aggregate

This work-in-progress, full-fidelity rebaseline reports aggregate outcomes for the author-original and GPT-5.6 Pro rewrite only. Every selected unit was included; there was no sampling. The V9 preparation made no provider calls. The aggregate retains six approved opaque SHA-256 commitments, plus totals and score bounds.

Both aggregate outcomes are `VALID`: author-original has coverage `0.9883` and score `63.0202` with bounds `62.0577` to `63.2243`; GPT-5.6 Pro rewrite has coverage `0.9905` and score `73.2369` with bounds `72.3575` to `73.3054`. The rewrite-minus-author difference is `+10.2167`; the bounds do not overlap, but this is not a statistical conclusion.

This result does not promote or change rubric wording, weights, criterion ownership, or HBQ-RS. Its closed public surface is limited to aggregate counts, totals, status, bounds, runtime identity, and opaque commitments.

```powershell
python evaluation-results/hbq-gray-blood-full-book-qpc24-rebaseline-v9-public-result-v1/verify_output.py
```
