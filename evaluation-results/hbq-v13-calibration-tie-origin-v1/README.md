# V13 calibration: where within-prompt ties came from

The [earlier V13 analysis](../hbq-v13-within-prompt-calibration-v1/README.md)
found 115 tied calibrated predictions among 203 within-prompt comparisons
where existing human reference ratings differ. This follow-up compares those
predictions with their retained original model scores.

| Within-prompt comparison, excluding reference ties | Original scores | Calibrated scores |
| --- | ---: | ---: |
| Agree with reference order | 57 | 57 |
| Disagree with reference order | 31 | 31 |
| Tie | 115 | 115 |

Every direction and tie was unchanged by calibration across all 240
pair/dimension cells, including the 37 reference ties. Thus all 115 ties in the
203 reference-different cells were already present in the original scores for
this panel. The finding concerns comparisons within a prompt, whose items share
one fitted transform. It does not contradict the previously reported changes
to pooled correlations across prompts, where transforms differ by fold.

The calculation uses the same 44 already-open TRAIN items and 22 folds as the
earlier analysis; 10 groups contain multiple items. It checks that the retained
raw scores reproduce every saved calibrated prediction exactly. This is a
post-result descriptive diagnostic, not fresh native admission, confirmation,
evidence of population performance, human validation, or a promotion decision.
The comparisons share works, raters and dimensions and are not independent.
No provider calls, new votes or endpoint pooling were performed.

`regenerate.py` requires the private digest-bound TRAIN schedule and calibration
output, the published calibration aggregate, and the retained response root.
It projects only score fields from retained responses and writes an aggregate;
no story, individual rating, model response, cell ID or private path is included
in the output. Schedule bytes contain frozen payloads; these are not decoded.

```text
python regenerate.py --schedule <private-schedule.json> --calibration <private-calibration.json> --public-result ../hbq-human-alignment-optimizer-v13-train-expansion-v1/calibration-result.json --response-root <private-response-root> --output <new-aggregate.json>
```

Expected aggregate SHA-256:
`93cbab6d779bd5858e9756eab901cc4e3cb804dc90c4611544e9c666957690d0`.
An independent ordered-pair recount reproduced all directions and ties.
