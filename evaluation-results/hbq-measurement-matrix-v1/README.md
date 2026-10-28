# Existing-measurement benchmark matrix

This package projects existing descriptive measurements into a common row schema.
It uses the existing public initial TTCW, reader-reference and selected-repeat
aggregates plus source-metadata.json. Regeneration requires no private aggregate,
story, individual rating, rater identity, native artifact, account or runtime store.
It computes no new correlation, score, bootstrap, confidence interval or inference.

From a repository checkout:

```
python evaluation-results/hbq-measurement-matrix-v1/regenerate.py --repo-root . --output matrix.regenerated.jsonl
```

The command writes a fresh file and prints its SHA256 for comparison with the
packaged matrix. Existing outputs are preserved. The expected coverage is
199 metric-family rows:126 TTCW,34 Dryad and39 Kyoto. This preserves the original
measurement coverage rather than byte equality with its private predecessor.
References are repository-relative or hash-only. The public package consists of
regenerate.py, source-metadata.json, matrix.jsonl and this README; preparation
records are not public inputs or required dependencies.

Each row retains dataset, population, declared CWR task scope, endpoint, requested
model/effort, arm, reference axis, cohort view, metric and unit. It copies the
source statistic subtree, point or distribution dictionary, statistic-specific
denominators, status and limitations. Source pointers identify the effective
public input. Reader aliases and supplemental-field pointers are explicit;
original input commitments remain separate from effective public input hashes.
The original private aggregate and matrix hashes are provenance, not files the
portable generator attempts to open. Efficiency-not-reported rows have a null
subtree and context pointer; they do not copy an entire private reader section.

The48-field supplement adds only existing uncertainty metadata omitted from the
public reader projection. For eight Dryad contrasts it retains interval95, seed,
draws_sha256, full_planned_missing_outcome_bounds and missing_bounds_type. For
four Kyoto differences it retains full12_missing_outcome_bounds and
bounds_are_confidence_intervals. All eight Dryad interval95 values are null,
including contrasts with zero undefined draws; no interval is reconstructed.
Bootstrap replication/undefined-draw counts already come from the public reader
input. Universal missing-outcome bounds are separate from confidence intervals.

TTCW marginal and pair-specific29/28 comparisons remain distinct from its common28
works across12 plot groups. Expert-derived pair directions are not direct human
preference ballots; majority test cells and individual ballots use different
units. Dryad common27 remains separate from pair-specific28/27 and planned30.
Kyoto fixed12 primary points remain separate from secondary exact-common
diagnostics; an11-story secondary result never replaces an unavailable primary.
Reader references, expert references and selected model repeats are separate
populations. Raw four-state leaf agreement, kappa, scalar comparisons, order
diagnostics and exact evidence-set overlap remain separate repeatability measures.
No human reliability ceiling or cross-population/form inference is supplied.

All prose.short_story form values are declared CWR task scope from retained
metadata, not new genre labels. Literal request endpoints bind TTCW and Dryad;
Kyoto's Sol endpoint is a logical requested route from requested_native/model,
explicitly not a literal endpoint field. Model/high values are requested settings.
The repeat public provenance's observed Sol/high/zero-tool summary is retained
separately. Requested settings and the retained observed-control summary have distinct
provenance; this projection makes no new native calls. Source-only Kyoto
constant/lexical diagnostics have native-model axes marked not applicable.

Accepted-only TTCW operations retain observed/missing counts for each token,
duration and TTFT metric. Cached/reasoning counters are subsets and are not added
to totals. Native task duration is not isolated inference latency, failed calls
and local waits are excluded, and summed request durations are not throughput.
Reader and repeat efficiency stay not_reported/null, never zero. Missing numeric
outcomes do not automatically mean abstention. No pooled estimate, winner,
intervention gain, calibration, promotion or independent confirmation is claimed.
