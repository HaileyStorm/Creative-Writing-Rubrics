# Czech poetry expert-reference metadata qualification

This provider-free check examines public metadata for the EduPo evaluation
corpus described in [Mareček et al. (2025)](https://aclanthology.org/2025.eval4nlp-1.9/).
It is a source lead, not a new CWR score or an admitted confirmation set.
The authors describe 100 Czech poems: 20 human-written and 20 from each of
four generation groups. The selection excludes free verse and non-metrical
poems. Their historical LLM evaluator was GPT-4o mini; its author-reported
settings, prompts and system-specific effects are not a current Sol collection.

At pinned repository commit `5740fbc2f7f32bf3257d5baf69747ad9958dc5ec`,
the combined annotation table has 100 rows and 18 fields. All 100 rows have
decimal-syntax entries in each of the eight inspected human/model dimension
comparisons; this checks presence and lexical form, not rating values, scale,
valid range or historical execution. The table has 100 unique filename keys;
their basenames match the 100 unique poem-tree filenames one-to-one. Exact
evaluation-relative paths do not match. The child and parent Git tree hashes
were reconstructed from metadata; poem contents were not fetched. A basename
match alone does not establish the bytes presented to historical judges or
the intended join and must not be used as native provenance.

The paper reports three experts for semantics, with their results averaged;
other dimensions have one expert each, including a replacement metre rater.
The combined table exposes one human-semantics column, and its header alone
does not establish how that column was produced. The paper states human and
LLM prompts use a 0–10 scale later normalized to 0–1, while raters were not
given common anchors. Table-specific transformations and row-level human
provenance remain to be verified before interpreting the numeric columns.

The authors' [analysis script](https://github.com/ufal/edupo/blob/5740fbc2f7f32bf3257d5baf69747ad9958dc5ec/evaluation/compute_results.py)
independently drops non-numeric values from each metric, checks only equal
column lengths, and then correlates the resulting lists. With different
missing rows but equal counts, that can pair different poems. A four-row
invented witness produces Pearson `0.866025` by that method versus `1.0`
for its two complete same-row pairs. The inspected columns in this particular
table have no presence mismatches, so this witness does **not** show that the
published results are affected. The paper's exact historical analysis inputs
and execution are not independently attested here.

The table and tree are public; per-poem rights, previous project/model exposure,
the exact text/annotation join, Czech-language judging capability, task and
rubric fit, and any prospective selection remain unresolved. The repository's
software license alone does not establish poem rights. No rating values, poem
text, model predictions, new human labels, or provider requests are included
or produced. Public paper-level findings were visible before this check, so
the cohort is not certified unused confirmation.

For reproduction, obtain the pinned `evaluation/annotations/all5.tsv` and the
recursive JSON metadata for Git tree `9348556886c5365dec644e54a3ff5f1a3f834325`,
then run `python metadata.py --table <local-tsv> --tree <local-tree-json>`.
The code checks both Git object hashes and the table's SHA-256 before producing
aggregate-only output. It processes the entire TSV as bytes in memory but
decodes only its header; it does not decode individual rating or poem fields.
The table, tree metadata, individual filename keys and original source files
are not redistributed by this package.
