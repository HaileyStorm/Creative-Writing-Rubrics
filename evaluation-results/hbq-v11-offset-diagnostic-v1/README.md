# Post-hoc offset diagnostic for a four-story development panel

A simple +1 shift of the baseline's six numeric scores, clipped to the human
reference range of 1–5, gives lower mean absolute error than the child20 prompt
on both historical endpoint results in this small, already-opened TRAIN panel.
The shift was chosen **after** the results were visible. It is not a frozen
comparator, learned calibration, new model judgment, or evidence of prospective
improvement.

| Historical endpoint | Baseline MAE | Child20 MAE | Baseline +1, clipped | Fixed 3 |
| --- | ---: | ---: | ---: | ---: |
| Sol | 1.338889 | 1.125000 | 0.791667 | 0.763889 |
| Grok | 1.041667 | 0.708333 | 0.569444 | 0.763889 |

Each result covers four prompt groups and six dimensions per group; lower MAE
is closer to the existing human means. Endpoints are separate. The clipped
shift has lower/equal/higher error than child20 on 3/0/1 Sol groups and 2/1/1
Grok groups. Without clipping, shifted MAE is 0.808333 for Sol and 0.569444
for Grok. One of 24 Sol shifted values was clipped; none was clipped for Grok.

Eleven of 24 Sol baseline numeric scores were below the reference scale's
minimum of 1; the saved profile describes finite numeric scores rather than a
proven 1–5 output constraint. Thus the shift partly changes the score scale.
The source Sol calculation includes one baseline dimension with false coverage;
this diagnostic preserves that original inclusion. Sol's fixed-3 predictor is
better than both shifted baseline and child20 here, and is also shown so a
shifted-model advantage over a constant is not assumed.

These four selected development groups do not establish a useful general
calibration, ranking quality, statistical significance, human alignment or
candidate promotion. Equal-group averaging, six dependent dimensions and
historical endpoint/provenance limits remain as in the original reports. Grok
is historical evidence only; no new contact was made.

`analyze.py` reads both pinned public Git results, checks their SHA-256 hashes,
validates within-endpoint group/reference pairing and reproduces the published
baseline and child20 means. Verify the saved aggregate with:

```
python -B evaluation-results/hbq-v11-offset-diagnostic-v1/analyze.py --repo . --verify evaluation-results/hbq-v11-offset-diagnostic-v1/aggregate.json
```
