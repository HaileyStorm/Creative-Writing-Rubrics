# Compact comparator: dimension scores and overall-score compression

23 October 2026. **Post hoc development evidence; no candidate is promoted.**

The retained Sol/TTCW comparison contains 17 assessed compact-comparator stories in 10 of the cohort's 12 plot groups. The comparator separately requests six dimension ratings and one overall rating, each from 1 to 5. Every observed overall rating is 2. This diagnostic asks whether the saved dimensions contain distinctions that the coarse overall category does not express.

The alternative is simply the unweighted arithmetic mean of the six existing dimension ratings. No score is fitted to human targets, no missing rating is filled in, and no model request or new human annotation is made. The diagnostic recipe was saved before computing its target association, but after inspecting score distributions and opening the development reference. It is therefore post hoc, rather than unused confirmation.

| Same 17 stories | Native overall rating | Six-dimension mean |
|---|---:|---:|
| Observed range | 2 | 1.667–2.167 |
| Distinct values | 1 | 4 |
| Tied unordered story pairs | 136 | 44 |
| Spearman correlation with existing expert scores | undefined | 0.639 |

The mean's exact support is 5/3 for one story, 11/6 for two, 2 for six, and 13/6 for eight. Every mean rounds to 2, matching the native overall category. Ordinary integer quantization could explain the constant overall ratings; this result does not show that the native judge aggregated its dimensions inconsistently. The prompt expressly asks for a separate overall judgment.

Four dimensions—character relationships, prose/voice, emotional reader effect and thematic complexity—are constant at 2. Only narrative architecture and worldbuilding vary, so the mean's ranking is exactly the ranking of their summed ratings. This is not evidence of six independent quality signals. Equal spacing and weighting of ordinal categories are declared operational assumptions.

The expert reference is the existing mean of 42 YES/NO ballots per story. An independent arithmetic review reconstructed the request-to-story joins, ballots, six-score means, tied ranks and correlation. Agent review adds no human validation.

Nineteen of the planned 36 stories are missing from this snapshot. The available subset is selected by collection progress and is too small to establish generalized improvement. The original constant score has **undefined**, rather than zero, correlation; there is no defined correlation gain against it. Correlations from HBQ's seven available stories or another unmatched subset cannot establish a method ranking. No bootstrap interval, significance claim or original coverage acceptance is reported.

The useful finding is narrower: saved compact dimension judgments contain target-associated ordering that the overall category does not express. Keep this fixed transformation as a development hypothesis for additional matched stories. Preserve the original compact comparator, canonical HBQ scores and live collection unchanged.

The [aggregate result](compact-dimension-mean-development.json) contains distributions, dimension frequencies and exact private-input commitments, without story text, work identities, raw ballots, responses or account details. The [reproduction script](compact_dimension_mean.py) requires the retained private inputs and the existing frozen analysis helpers:

```text
python compact_dimension_mean.py --joined FIXED_JOINED321 --manifest MANIFEST216 --freeze ANALYSIS_FREEZE258 --labels OPEN_TTCW_DEVELOPMENT_REFERENCE --repo CWR_CHECKOUT --output NEW_AGGREGATE_JSON
```

The script pins the 338-result view and uses exactly its 17 compact results. It never reads the growing collector journal. The original stopped comparison and its [coverage and provenance limits](README.md) remain historical evidence. This supplement does not replace them or establish prospective confirmation, other-form validity, repeatability or completion of the full research program.
