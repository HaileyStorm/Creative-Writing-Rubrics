# Retained LAMP ordinal development comparison

20 October 2026. **Inconclusive retrospective development evidence from a fixed saved prediction prefix.** This compares available initial Sol predictions with existing human rankings within three-passage groups. It adds a second human-reference dataset alongside the contemporary TTCW report, while preserving the different historical collection conditions.

## Observed agreement and coverage

LAMP supplies 94 groups of three passages, with three source assessor rankings per group. Those 282 rankings yield 282 canonical passage pairs and 846 correlated human pair ballots. Earlier ranking positions are preferred. There is no absolute human scalar quality score and no valid global score correlation across the disconnected groups.

For each scalar method, the higher saved score defines its direction on a pair. A model tie receives half credit against a human preference. The table uses the human-majority direction from the three source rankings.

| Method | Numeric passages / 282 | Available pairs / 282 | Model ties | Majority half-credit / available pairs |
|---|---:|---:|---:|---:|
| HBQ | 38 | 5 | 0 | 4 / 5 (80.0%) |
| TTCW14 | 52 | 10 | 4 | 5 / 10 (50.0%) |
| Holistic | 37 | 6 | 5 | 2.5 / 6 (41.7%) |
| Compact | 43 | 9 | 5 | 6.5 / 9 (72.2%) |
| Oregon | 40 | 2 | 0 | 2 / 2 (100.0%) |
| Pairwise, both-order consensus | — | 4 | 0 | 1 / 4 (25.0%) |

**These methods cover different pairs. The table cannot identify a winner.** HBQ shares zero usable pairs with each scalar comparator and with the both-order pairwise consensus. Every paired performance contrast is therefore undefined. No method has a complete three-passage group for a full within-group comparison.

The individual-ballot agreement is 12/15 for HBQ, 15/30 for TTCW14, 7.5/18 for holistic, 18.5/27 for compact, 6/6 for Oregon and 3/12 for the four both-order pairwise cases. Fractional totals reflect the prespecified half credit for model ties. These ballots are dependent observations from existing rankings, not additional human participants or independent samples.

## Pair orders: stability and human agreement differ

There are 93 accepted initial ordered pair requests, covering 89 distinct pairs. Four pairs have both AB and BA presentations; 85 have only one presentation. The native answers contain 55 A choices, 37 B choices and one explicit tie. A and B are mapped back to the actual passage identities before comparison.

All four completed AB/BA pairs retain the same actual passage preference after display reversal. Only one of those four preferences agrees with the human majority. This small subset illustrates why order consistency does not establish human agreement. It is not evidence about same-order repeats, a causal order effect or a representative population.

Across all 93 observed orders, majority agreement is 44.5/93 (47.8%), and individual-ballot agreement is 128.5/279 (46.1%). There are 564 planned initial orders, leaving 471 unobserved. The two orders of a pair reuse the same existing human ballots; they do not create new reference judgments. These order-level fractions must not be compared as though they covered the same cases as the four-pair consensus or the scalar methods.

## Method and exposure boundary

This descendant analysis fixes the already-admitted 032 prediction files: 1,149 accepted Sol requests from the saved 1–1,155 prefix, alongside four semantic rejections and two empty terminal records. It reuses saved scores and complete HBQ banks without rescoring, repairing or resending any request. A fixed saved prefix does not prove that the original campaign is terminal or that reservations can be released.

The parent study retains its all-17,808-terminal and explicit human-release contract unchanged. That contract is not met here. `analysis-freeze.json` instead defines this separately named retrospective development computation, with its prediction pins, pair selection, tie rule, denominators and limitations fixed before this execution decoded the six retained ranking files. The pinned human profile already classified all six strata as development-exposed. This is not a blinded analysis or unused confirmation, including for historical source files whose names contain “confirmation” or “holdout.”

The frozen original lineage and rank-decoding functions verify source membership, paragraph identities, rank permutations and extraction receipts. They preserve source order as the preference direction; source roles do not determine a preference. The original collection/admission entrypoint and its release gate are not executed or modified.

Every primary method remains an incomplete, availability-selected comparison. No bootstrap resamples, confidence intervals, significance tests, winning-method selection or candidate promotion are reported. `results.json` includes arithmetic full-denominator missingness bounds; those are not statistical intervals. The eleven source assessor IDs are not verified as eleven independent people. Paragraphs, pairs and rankings share source groups and assessors.

Historical tool controls and effective backend/account/sampler equivalence remain unqualified. Keep this condition separate from the current tools-disabled Sol study. There are zero provider calls, canonical scorer calls, semantic/native replays, new human labels or judge training in this computation. Independent agent review is not human validation.

## Reproduction and retained sources

The actual command accepts the original frozen study directory, the saved 032 prefix, its pinned human profile and original analysis source, the private control root, this analysis freeze, and a new output directory:

```text
python analysis.py --frozen FROZEN_DIRECTORY --prefix SAVED_032_DIRECTORY --human-profile HUMAN_PROFILE_JSON --original-analysis ORIGINAL_ANALYSIS_PY --control PRIVATE_CONTROL_ROOT --freeze analysis-freeze.json --output NEW_DIRECTORY
```

The output directory includes private reconciliation and target-opening records. Publish only the aggregate `results.json`. The private records and original text/labels are excluded from this package. Reproducing the source joins requires authorized access to the retained private inputs.

The real saved-data execution completed successfully. Independent review reproduced every agreement count, tie credit and arithmetic bound from the private reconciliation ledger, checked all 93 native A/B mappings and sampled two human-source joins. It did not rerun collection, admission, scoring or the full human decoder.

`analysis-freeze.json` pins the exact source and inputs. The main commitments are:

| Input | SHA-256 |
|---|---|
| Original frozen manifest | `480aa86df271078e322ac85cf8cfe5fe6ed02344138e218900cfe03c069b6ab6` |
| Saved bank profiles | `aa6a9e809f53e6640497e7fa3d5efe6f583426b794a90f031832562cb7354a69` |
| Admitted predictions | `72ad3b80421137f29e36f85efab1d8b8314bc2d1a67dd550959befb0cb052325` |
| Human ordinal profile | `cd90bc17ae1ea1e0f2113f7c2b497eb47c59962a8891a91c1883bb3865b121e5` |
| Original analysis/decoder source | `de4e20855e346232a0de7f7fbbc83b6f85b9982fc992821cfe962344e6c4d856` |

Human-reference provenance follows [Salesforce creativity_eval](https://github.com/salesforce/creativity_eval/tree/3d029879df6878f611363db88cc02d465699bc51). Underlying noncommercial and redistribution restrictions remain in force. No source prose, raw human rankings, assessor identifiers, private paragraph identities or operational account details are distributed here.
