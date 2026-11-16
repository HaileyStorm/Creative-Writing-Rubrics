# HF32 measurement-matrix supplement

This supplement puts the published HF32 common-cohort comparison and its later
word-count baseline into ten source-linked rows. It extends the coverage of the
[existing measurement matrix](../hbq-measurement-matrix-v1/README.md); it does
not change that historical matrix or compute new statistics. All inputs are
already-public aggregate files. No stories, individual ratings, model responses
or private inputs are needed to regenerate these rows.

For each of two human-reference axes, four rows retain signed Spearman
correlations for historical HBQ, frozen candidate 708, TTCW14 and word count.
The fifth retains the historical-HBQ-minus-TTCW14 contrast and its conditional
work-exchangeability sensitivity range. Each axis uses 19 works with the three
scored arms and that human reference available; 21 have all three scores, and
13 of the original 32 are absent from each paired comparison. The expert and
reader cohorts need not contain the same works. Word count was selected after
the original result was available.

Historical and candidate scores use the same underlying verdict banks, and
candidate 708 changed none of the 27 complete banks. The two reference axes are
different constructs. The conditional ranges are not population confidence
intervals or cluster-aware uncertainty. Results are selected development
evidence and do not establish a winner, human validation, generalization or
candidate promotion. The historical model contexts have mixed qualifications;
the source does not recertify them as current-account, tools-disabled execution.
Form and model settings are not inferred from these aggregate files.

The [original HF32 report](../hbq-hf32-frozen708-human-reference-v1/README.md)
documents target definitions, attrition, score scales and retained failures. The
[length report](../hbq-hf32-length-baseline-v1/README.md) defines its word
count and the matched cohort. Source pointers and SHA-256 commitments are
retained in each row. The supplement does not cover every metric required by
the larger benchmark program.

From the repository root, write to a fresh output path:

```text
python evaluation-results/hbq-hf32-measurement-matrix-v1/regenerate.py --repo-root . --output hf32-matrix.regenerated.jsonl
```

The command checks both input hashes, cross-checks published common-view values,
and refuses to overwrite an existing output. The expected output SHA-256 is
`ff72cf5c9413ff3b17b52882311eee88228e12d1975d6f2561fed0978bf2c6d2`.
