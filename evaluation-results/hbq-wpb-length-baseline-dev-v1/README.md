# WritingPreferenceBench development: a length baseline

On the 129 already-opened English WritingPreferenceBench pairs in the existing compact-family development screen, a deterministic rule that selects the longer response matched the recorded preference on 84 of 105 TRAIN pairs and 17 of 24 DEV pairs. The rule counts Unicode code points, including whitespace; ties are not wins. There were no equal-length pairs in these two partitions. Each category has three pairs, so category-macro and pooled win proportions agree.

| Method | TRAIN wins / pairs | DEV wins / pairs |
| --- | ---: | ---: |
| Longer response | 84 / 105 (80.0%) | 17 / 24 (70.8%) |
| Grok compact-family proxy | 70 / 105 (66.7%) | 10 / 24 (41.7%) |
| Sol compact-family proxy | 61 / 105 (58.1%) | 11 / 24 (45.8%) |

The model numbers are from the existing [matched Sol development result](../hbq-human-alignment-wpb-sol-completed-result-v1/README.md); ties count as non-wins for all three methods. The compact-family method is a coarse, handcrafted proxy and not a canonical full HBQ evaluation. The model evidence has the qualification limits described in that result, including no native-admission claim and incomplete provider-side identity attestation.

The length rule was chosen after the original development results were available, although its exact calculation was specified before this analysis. These small, category-clustered, selected development pairs do not establish causation, statistical superiority, general performance, or agreement on the 24 held-back confirmation pairs. A length difference does not tell us why people preferred an answer. The frozen confirmation outcomes remain closed for this analysis. No new model requests or human annotations were made.

The benchmark is [WritingPreferenceBench](https://github.com/WritingPreferenceBench/Writing-Preference-Bench/tree/c6ac5821582e77fb34d27f6b54aac937904ee112), by Ying and colleagues; see their [paper](https://arxiv.org/abs/2510.14616). The existing [CWR pilot](../hbq-human-alignment-wpb-pilot-v1/README.md) pins the source and describes its category-level split. The source card's machine license tag and its prose disagree; this result distributes no dataset records, response texts, labels, or category-level results.

With access to the exact previously frozen r3 inputs, `python regenerate.py --run --freeze-root PATH` checks the frozen hashes and recipe, selects the default TRAIN/DEV schedule, and prints aggregate counts. It scans the full files as bytes but does not decode the excluded confirmation rows or target score fields. It does not download data or invoke a model. The source freeze is not included here. The reference counts were independently recounted using the same reviewed selection boundary and a separate aggregation.
