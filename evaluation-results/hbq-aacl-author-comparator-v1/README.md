# Retained AACL author-model score distributions

This retrospective development analysis summarizes the authors' **public**
Study 1 model-rating table from Sathya, Huang and Cheng, [A Framework for
Evaluating AI-Generated Creativity](https://aclanthology.org/2026.aacl-long.203/).
It reads no human ratings and contains no CWR judgments. It reports the initial
creativity rating, not the later reflective rating. The [source table at the
pinned revision](https://github.com/ku-nlp/creativity-evaluation-artifact/blob/120c47958bd4941e8d6abd6995dc858b53515788/study1_human/data/llm_ratings.csv)
contains 20 historical model conditions on 12 story IDs from three topics.

All 240 entries are valid integers on the native 1–7 scale. Of these, 87 are
7 and none is 1. Within each condition, 478 of 1,320 unordered story-pair
comparisons are score ties; restricting pairs to the same topic gives 108 of
360 ties. Counts reuse the same 12 stories across conditions.

For the 178 unordered pairs of conditions with different recorded model IDs,
the models assigned the same score in 1,025 of 2,136 same-story comparisons.
Across their 11,748 condition-pair/story-pair comparisons, the models gave the
same strict direction 5,163 times and opposite strict directions 302 times;
both tied 2,266 times and exactly one tied 4,017 times. The separate 12 pairs
with the same recorded model ID have 445 same strict directions, three
opposite, 189 both tied and 155 one tied, among 792 comparisons. Full
within-topic counts and unavailable-value accounting are in `result.json`.

These are descriptive historical outputs. The stories, topics, model families
and settings are reused, so pair counts are not independent observations.
Different model IDs do not establish independent implementations or runtimes.
The authors' released model-story and survey-story strings are not always
byte-identical; actual model inputs and participant rendering are not proved
by this table. A model's score distribution, tie or agreement does not prove
quality, human alignment, causal effects, population reliability or superiority.
No new model call, human judgment, prospective confirmation or candidate
promotion occurred; the full research program remains incomplete.

The authors' [data license](https://github.com/ku-nlp/creativity-evaluation-artifact/blob/120c47958bd4941e8d6abd6995dc858b53515788/DATA_LICENSE.md)
identifies the source data as CC BY 4.0. This report credits the authors and
contains derived aggregates only; it does not redistribute their source table
or individual story scores.

To reproduce, obtain the pinned source table and run:

```text
python evaluation-results/hbq-aacl-author-comparator-v1/regenerate.py --input llm_ratings.csv --output regenerated.json
```

The input must have SHA-256
`0c6deb17a57ed5d04f7a0c42388ada259924e85ba0112829571df16f84f06f37`.
The expected output SHA-256 is
`48beda6026337c07d2d0936204342178366f17627adfc8bb981012b34106ec35`.
