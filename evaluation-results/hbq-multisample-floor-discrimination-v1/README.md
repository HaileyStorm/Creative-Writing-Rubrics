# Historical matched scalar floors and discrimination

This provider-free extension uses the completed, already-opened HANNA development
repeat panel: six arms, eleven items and five repetitions, with 330 retained
scores. It reports the original six-item HBQ cohort and later five-item HBQ
cohort separately, applying identical cohort membership to every comparator.
The profile was frozen before metric execution. No pooled HBQ primary result is
produced, and existing analyses and source artifacts remain unchanged.

## Verified aggregate measurements

The single completed execution retained all 330 scores. Independent readback
recomputed the extreme rates and between-item ties directly from the selected
scalar values. Counts below retain their full denominators; near floor means
at most 10 percent of the declared native range, after subtracting its minimum.
The last two columns count tied item pairs using five-repeat means.

| Arm | Original exact floor /30 | Later exact floor /25 | Original near floor /30 | Later near floor /25 | Original tied pairs /15 | Later tied pairs /10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HBQ | 4 | 15 | 23 | 20 | 0 | 1 |
| Compact analytic | 25 | 25 | 25 | 25 | 10 | 10 |
| Holistic anchored | 25 | 25 | 25 | 25 | 10 | 10 |
| Cambridge | 0 | 0 | 0 | 1 | 0 | 1 |
| NAPLAN | 0 | 0 | 0 | 0 | 0 | 0 |
| Oregon | 1 | 1 | 10 | 5 | 0 | 1 |

No arm reached its exact native maximum. Compact and holistic each have two
distinct item means in the original cohort and one in the later cohort, so
their repeat stability coexists with substantial floor compression. This does
not establish which arm judges quality better. The different items and HBQ
versions prevent a causal interpretation of the cohort differences. The
regenerated report also retains near-ceiling rates, per-repetition ties and all
80 descriptive paired extreme-rate intervals.

Completed report SHA256:
`198005925d4ca220b12803e9ffdc7ad28893046bf5474d3b125a4018c4ffef15`.
Only aggregate measurements and commitments are published here; retained
input-level projections and private execution receipts remain local.

For raw repeat scores and item repeat means separately, the report gives exact
native minimum/maximum rates, near-extreme rates after the declared affine
mapping (at most 10 or at least 90), distinct scores, complete denominators and
missingness. Between-item ties are separate from within-item repeat agreement:
they are reported for each of five repetitions and for item repeat means.
Native ranges are extracted from the pinned historical `_scale` function.

The pinned lexical reader is extracted without modification, with its `json`
namespace bound to a standard JSON decoder using `Decimal` for decimal tokens.
Only item/prompt commitments, scalar values and cohort membership are selected;
all arithmetic uses `Fraction`, with no epsilon, clipping or binary-float
roundtrip. Human targets, quality bands/cutpoints, prose, rationales and response
bodies are skipped. Consolidation provenance is hashed without decoding.

The extension uses 1,000 paired prompt-cluster bootstrap draws with seed560820
for comparator-minus-HBQ extreme-rate differences, separately for raw-repeat
rates and item-mean rates. Each draw samples the same clusters for all arms;
items sharing a prompt stay together. Percentiles use exact linear interpolation.
These descriptive intervals have only six or four clusters and make no quality
or multiplicity-adjusted claim. They do not replace the original analysis's
10,000-draw MAPD bootstrap.

```powershell
.venv\Scripts\python.exe -B evaluation-results\hbq-multisample-floor-discrimination-v1\analyze.py `
  --source-root <pinned-consolidated-source-directory> `
  --output-root <fresh-controller-owned-directory-outside-repository-and-inputs>
```

The command refuses an existing output and any missing, changed, nonfinite,
out-of-range or unmatched score. It writes `report.json`, source/profile
snapshots and a terminal receipt after readback. Public report fields contain
aggregate measurements and commitments, without input identifiers or local paths.

This is historical development evidence. It does not establish calibrated
absolute quality, contemporary model performance, human-alignment improvement,
or a causal rubric-version effect. Saved scalar/native evidence is inherited;
no native, semantic or source-body reconstruction runs. Historical tool-disabled
declarations do not certify actual past tool removal, backend identity or
physical contact cardinality. No provider call or new vote is made.
