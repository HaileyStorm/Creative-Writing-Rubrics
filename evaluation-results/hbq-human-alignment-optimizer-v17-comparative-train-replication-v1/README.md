# V17 comparative HANNA TRAIN replication

V17 repeats V16's unchanged direct/comparative judging method on the next five
frozen TRAIN prompt groups. It is a replication measurement, not a candidate
selection exercise and not a new CWR default. It tests whether the V16 pattern
persists beyond V16's first five best-covered TRAIN groups.

The original V15 TRAIN group order is descending observed item count and then
ascending prompt-group hash. V16 consumed positions 1--5. V17 predeclares
positions 6--10:

- `prompt-c85edd8245f2bf73` (3 V15 direct items)
- `prompt-ea26ed67b3d13cb8` (3)
- `prompt-3ea05aae03d4b979` (2)
- `prompt-6b7fff0c3794370c` (2)
- `prompt-933b864147df69bd` (2)

Each group is completed to the ten original non-Human HANNA systems. V17
reuses all 12 exact V15 individual-direct cells in those panels, creates 38
fresh individual-direct cells, and creates ten comparative cells: one
ten-story batch in each opposite order for every group. That is 48 scheduled
fresh calls and 60 measured cells per endpoint; individual direct remains
historical and noncontemporaneous. Grok and Sol must receive byte-identical
payloads for each cell and must remain endpoint-separated.

The V15 direct task/profile/schema and V16 comparative task/profile/schema are
loaded only after exact source-and-Git-blob validation. V17 changes only its
study identifier and the selected local stories. Human targets remain local;
no outbound payload includes a target.

For direct, forward, reverse, and the per-story mean of opposite orders, the
analysis reports six-axis HANNA-compatible within-prompt average-tie Spearman
with retained/dropped prompt IDs and counts, strict all-five coverage, global
story rank correlation, MAE, and model-tied pairs. Constant per-prompt scores
are undefined, never zero. The comparative mean is the predeclared primary;
neither order may be chosen after seeing results.

Pinned inputs: V15 study `4afeaff679efaf37e702c08841eb30a3317693e677ecfc3ded4dbb4ae4710caf`,
V16 study `8e24c0e0469339b3ad0a168bfb4aa5d4532c9cfea85a95d72764dc30037c34aa`,
V16 contract `3d0aaee0e4e37e73d50cbd37969f006ac8b90deeebd74caa9512d323c94d7eb8`,
split manifest `6ffa942b595449f4118c2cd51f3a36716126612a7c10f4765953c17eb1efdbc2`,
HANNA CSV `ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b`,
and frozen successor contract `b0f6dd24415c388a3104f8c9304ce301193cf0a48631a86c4886bc8ce48468e7`.

This package is provider-free source only. An executor, route disclosures,
native lifecycle admission, results, DEV/confirmation, endpoint pooling,
promotion, and runtime use are all explicitly **NO-GO** here.
