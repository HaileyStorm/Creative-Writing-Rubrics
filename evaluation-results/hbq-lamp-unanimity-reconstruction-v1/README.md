# LAMP agreement and disagreement: public-aggregate reconstruction

This retrospective development note reconstructs a breakdown that is already
determined by the [published LAMP aggregate](../hbq-lamp-stopped-development-20261020/README.md).
It does not open or publish individual rankings, passage text or model responses.

| Existing human votes on pair | Saved presentation orders | Distinct pairs | Model agreement with majority | Model agreement with individual ballots |
| --- | ---: | ---: | ---: | ---: |
| Unanimous | 70 | 66 | 30.5 / 70 | 91.5 / 210 |
| Two to one | 23 | 23 | 14 / 23 | 37 / 69 |

The half credit is from the original model-tie policy. All four pairs presented
in both orders are in the unanimous stratum, so the 93 orders represent 89
distinct pairs and four orders reuse the same ballots. These strata contain
different, availability-selected passages; they do not identify an effect of
human disagreement or a winning method. Shared passages, groups and assessors
also preclude treating the individual ballots or orders as independent samples.
Historical controls and endpoint equivalence remain unqualified.

For each unanimous order, ballot credit is three times majority credit. For
each two-to-one order, ballot credit equals majority credit plus one, including
the half-credit tie case. The source reports 70 unanimous and 23 split orders,
44.5 total majority credit and 128.5 total ballot credit. Solving these two
equalities gives the table. Choosing the observed majority on every order would
score 210/210 and 46/69 against those same ballots; those are in-sample arithmetic
maxima for binary decisions, not external reliability or population ceilings.

No new model call, native admission, human label, statistical test, confirmation,
human validation or candidate promotion occurred. The full research program
remains incomplete. The source's paired model comparisons are undefined because
the original HBQ and comparator pairs do not overlap.

Regenerate from the public repository without private inputs:

```text
python evaluation-results/hbq-lamp-unanimity-reconstruction-v1/regenerate.py --repo-root . --output lamp-unanimity.regenerated.json
```

Expected SHA-256: `ac0df4b7e184c77c2472e6e9374edd68b8086353bbe9e9fbeaa71d4fe38b8830`.
