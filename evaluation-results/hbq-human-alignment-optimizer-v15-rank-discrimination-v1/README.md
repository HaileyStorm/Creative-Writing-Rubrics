# V15 matched HANNA rank-discrimination experiment

This development-only package compares two output forms on the same frozen 48 TRAIN stories and 24 prompt groups: six direct 1-5 criterion scores and six cumulative four-threshold score encodings. It has no DEV or confirmation rows, no selection or promotion authority, and no endpoint pooling.

Every condition receives the same story, prompt, and faithful (not verbatim) HANNA Appendix A Table 7 anchors, with the source URL frozen in the schedule. The threshold condition stores its raw bits and projects each dimension deterministically as `1 + count(passed thresholds)` only when the bits are cumulative; malformed or nonmonotonic answers are invalid and never repaired or resent.

Grok is the primary endpoint (96 logical cells, maximum concurrency 10). Sol is a separate later replay of each frozen cell's exact payload bytes. Reports retain finite-score coverage counts, invalid counts, ties and score occupancy, MAE, fixed-three context, pair accuracy for unequal human targets, and tied-rank correlations. Group aggregates use the exact scheduled item identities per prompt group; no uniform group size is assumed. The primary rank metric is the mean of six item-level 48-item Spearmans; it is undefined when any dimension is constant.
