# EduPo source groups and historical-output provenance

This provider-free follow-up to the [poetry metadata check](../hbq-edupo-metadata-qualification-v1/README.md)
examines source-group and filename metadata without decoding individual scores
or opening poem contents. The table contains five source tags of 20 rows each;
one tag is `CCV`, matching the paper's description of the human-written source.
All 100 table paths share one parent and their uniquely matched tree files share
one other parent. Neither complete path is a suffix of the other. These facts
are consistent with a systematic path change, but do not authenticate an exact
historical file-to-score join or prove which bytes a judge received.

The [public Corpus of Czech Verse repository](https://github.com/versotym/corpusCzechVerse/tree/c3741e853238fe5f2c671008b57e4ef82ed354c5)
says it contains 1,305 of 1,689 books, while 384 remain copyrighted. Its
[pinned README](https://github.com/versotym/corpusCzechVerse/blob/c3741e853238fe5f2c671008b57e4ef82ed354c5/README.md)
identifies its release as CC-BY-SA and points to version 4.0; it requests
attribution to the Institute of Czech Literature. It also notes that the same
poem may occur in multiple editions. The 20 `CCV` tags do not identify the
underlying books or prove that they are in that particular release. Rights for
the actual items, editions, annotations and generated sources remain unresolved.

At the pinned EduPo revision, `evaluation/evaluate_poems.py` writes a header
containing `filename` and five named measures. The saved `automatic.tsv` header
contains `filename` and ten measures, so it cannot be the unchanged direct
output of that exact script. A different revision, processing or merge may
explain the difference; this check does not determine what was run or imply
that the scores are wrong. This is relevant before claiming that saved model
scores, prompts and source bytes are fully bound.

Run `python scope.py --combined <all5.tsv> --tree <recursive-tree.json>
--automatic <automatic.tsv> --evaluator <evaluate_poems.py>` to reproduce the
aggregate. The code checks the original Git blob and tree hashes, reuses the
pinned preceding metadata checker, and inspects the evaluator's header-writing
syntax without executing it. Both tables are held as bytes in memory; only
headers and source-group metadata are inspected. Individual scores, filenames,
poems and raw source files are not included in the output or this package.
No CWR judgments or new human labels are produced, and the data are not yet an
eligible unused confirmation set.
