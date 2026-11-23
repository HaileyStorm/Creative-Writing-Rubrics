# HANNA seven-group paired error sensitivity

The existing [Sol development result](../hbq-human-alignment-optimizer-v5-f20-broader-development-sol-result-v1/README.md)
reports mean absolute error (MAE) for the same seven prompt groups under a
baseline, a parent profile and descendant 13. This retrospective reanalysis
uses only its public per-group MAEs. Within each group the published source
reports error averaged over six rating dimensions; each group has equal weight
in the overall result. Lower MAE is better against that study's existing human
reference, not a direct literary-quality score.

| Comparison | Groups with lower / higher / equal error | Mean change in MAE | Range of leave-one-group-out mean changes |
| --- | ---: | ---: | ---: |
| Baseline → parent | 5 / 2 / 0 | -0.093651 | -0.150926 to -0.037037 |
| Baseline → descendant 13 | 4 / 2 / 1 | -0.180159 | -0.252778 to -0.126852 |
| Parent → descendant 13 | 4 / 3 / 0 | -0.086508 | -0.112037 to -0.053704 |

Each change is right minus left. The leave-one-group-out range is calculated by
omitting each of the seven groups in turn and averaging the remaining six. In
this saved dataset the mean change remains negative under each omission, even
though some individual groups worsen. That is a finite sensitivity check, not
a confidence interval, significance test or proof of generalization. It says
nothing about variation within groups or individual raters.

The source result is a selected, already-open development comparison; the
descendant was chosen using separately reported historical Grok development
evidence. The historical Sol settings and receipt claims retain the source's
limitations. This analysis does not independently replay its 21 process
records or authenticate native/provider contact, account, enabled tools,
human-reference construction or complete source population. It does not pool
endpoints, establish a stronger comparator, reopen confirmation, or promote a
profile. Shared stories, prompts and evaluators may create dependencies.

To reproduce from a clone containing the pinned commit, run:

```sh
python evaluation-results/hbq-hanna-seven-group-sensitivity-v1/analyze.py --repo . --verify evaluation-results/hbq-hanna-seven-group-sensitivity-v1/aggregate.json
```

The program checks the source Git object's SHA-256, matches all three profiles
on the same seven group IDs, and recomputes the descriptive summaries. It reads
no private evidence, story text, new human labels or provider data, and makes no
model calls. The [aggregate](aggregate.json) omits individual group IDs.
