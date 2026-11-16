# WritingPreferenceBench development matrix supplement

This supplement projects six already-published aggregate results into rows for
the [existing measurement matrix](../hbq-measurement-matrix-v1/README.md). It
does not calculate new model scores or access private data. The source is the
matched compact-family result and its later length-baseline report.

| Arm | TRAIN wins / pairs | DEV wins / pairs |
| --- | ---: | ---: |
| Longer response | 84 / 105 | 17 / 24 |
| Grok compact proxy | 70 / 105 | 10 / 24 |
| Sol compact proxy | 61 / 105 | 11 / 24 |

Ties count as non-wins. The length rule counts Unicode code points including
whitespace and was selected after the model results. The compact-family method
is a handcrafted proxy, not a full HBQ evaluation; its original native admission,
provider identity and reasoning qualifications remain unproven. The selected
development pairs share categories, and these marginal counts do not establish
causation, statistical superiority or performance on held confirmation pairs.
No rater expertise or new endpoint control is inferred. See the [matched
result](../hbq-human-alignment-wpb-sol-completed-result-v1/README.md) and
[length report](../hbq-wpb-length-baseline-dev-v1/README.md) for definitions,
source restrictions and limitations.

The generator verifies the public aggregate and the public length-report bytes,
copies their counts and writes a fresh JSONL file. It needs no source texts,
individual ratings, private inputs or provider service. From the repository root:

```text
python evaluation-results/hbq-wpb-measurement-matrix-v1/regenerate.py --repo-root . --output wpb-matrix.regenerated.jsonl
```

Expected SHA-256:
`f37ff470c1b89170a479ab6ce0bd08a41a6fa216c54a2b8b0799f2e12c48ae1e`.
