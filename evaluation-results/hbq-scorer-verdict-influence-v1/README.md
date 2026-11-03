# Short-story scorer influence diagnostic

This package records finite mechanical influence through the actual canonical
`hbqrs.core.compile_bundle` and `hbqrs.core.score_bundle` implementation. The
public v2 wrapper delegates scalar scoring to this core. This diagnostic excludes
v2 confidence diagnostics, strict import admission and native judge admission.
`aggregate.json` is the unchanged reviewed aggregate; this package adds no scorer
execution or additional experiments.

## Fixed recipe and denominators

The bundle is `prose.short_story`, bundle version 1, HBQ-RS 1.2.1. Its 178 selected
questions comprise 143 domain questions, 18 bounded negative-penalty questions,
17 unscored supplementals, and **zero hard gates**.

Before scoring, source bytes, the recipe and two complete synthetic verdict banks
were frozen. Questions are sorted lexicographically by public question ID. Bank A
alternates YES/NO by that global index; bank B complements A. The stipulated rule
that gates pass is vacuous here. Typed synthetic summary references satisfy
reference-count requirements mechanically and assert no source grounding.

Each bank independently changes each question to each of its three other raw
states: YES, NO, NOT_APPLICABLE or CANNOT_ASSESS. Every simulation clones its
original complete bank; effects are never accumulated. This yields **1,068 flip
reports plus two baselines: 1,070 actual core score calls**, zero provider calls
and zero bootstrap. Weights and historical replay semantics remain unchanged.
Banks were not selected or tuned after outcomes.

## Observed effects

The baseline final scores were 37.6799 (A) and 38.3201 (B), both with coverage 1.
Of 1,068 flips, 953 changed the observed total, 286 changed positive coverage,
957 changed final bounds, and 322 produced a nonzero final interval width.
Coverage ranged from 0.98 to 1; observed totals ranged from 35.0132 to 42.3201.
Changes from each original baseline ranged from -2.6667 to +4.0 points; interval
widths ranged from 0 to 2.6667 points.

All 1,068 results remained SCORED. Null totals, INELIGIBLE, UNRESOLVED,
PROVISIONAL and gate-status changes were zero. No selected gates means this
package does not demonstrate gate-triggered ineligibility.

Each result was compared with both fixed baseline banks: 2,136 comparisons,
including comparisons with its own original bank. There were 1,010 LESS,
1,011 GREATER and 115 TIE results; no NULL or unavailable comparisons. Of the
1,068 comparisons with the other fixed bank, 114 strictly reversed the original
ordering: 58 GREATER-to-LESS and 56 LESS-to-GREATER. Ties use exact equality of
the scorer's reported rounded observed scores. Eligible ordering requires both
statuses to be SCORED; raw numeric ordering is retained separately.

All 108 penalty flips changed numeric projections. All 102 supplemental flips
preserved numeric/status projections. Of 858 domain flips, 853 changed numeric
projections. Historical cumulative holistic-ladder normalization is preserved,
including original normalization issues. Two single raw flips restored a higher
raw YES previously normalized to NO; each changed two effective states and
produced a +4.0-point total effect. Raw and effective changes remain explicit.

## Interpretation and limits

These are two artificial mechanical banks, not real stories, native model
verdicts, human labels or literary truth. Hypothetical NOT_APPLICABLE and
CANNOT_ASSESS states stipulate activation or evidence availability solely for
the simulation. The results show finite conditional scorer effects, not global
sensitivity, useful real-world ranking, human alignment, full-system validity,
full v2 behavior, or completion of the broader research program. Negative
penalties, supplemental roles, uncertainty bounds and ladder normalization are
part of the measured historical behavior, not proposed policy changes.

## Exact SHA-256 identities

All paths below are public repository-relative source paths. Canonical JSON
objects and generated packets use the frozen serialization identified by hash.

| Source or frozen object | SHA-256 |
| --- | --- |
| `src/hbqrs/core.py` | `70b4cd16bd536f2f6ddb8e066f801090a037a39605652b14d6c7f6ff312446cb` |
| `registry/all_modules.json` | `43a33ee015310097f79c8a04bb7c3a8782813e758d523b1db08ae2b14d51f66f` |
| `bundles/all_bundles.json` | `012af060e8630b8980661465b368e129ddeec82dfa7b48e13e7a35a473eb95a8` |
| `bundles/prose.short_story.yaml` | `444040ef7c3c769146f597ecd3bfa28ddf5b4b1aaadde3ac93da4dccd02e67d8` |
| `src/hbqrs/__init__.py` | `41ae50c616e18a2a46245ca838449a71ddd34ad952c3f033d5ca0a0308b9ba24` |
| `src/hbqrs/scoring_v2.py` | `1305f444aaa45a0f47cc38cab207e847ae2ca04142637e6ee765edc3f06960d6` |
| `src/hbqrs/cli.py` | `5d8edde178079eb47be20b5e8434c865aab846be06b087af6d3de3aadf1ce913` |
| Frozen selected bundle object | `d17c61ed85026eb7d82363f85e8af20b5a207b4b6bb9c3307bbea3eb22e9c707` |
| Frozen compiled packet | `f11f55e8263e3fcc8a2d4b9a00021cf34f0ba2acac843e530999d1ed845fe2f8` |
| Frozen recipe | `87474dbb64f004b25809217a25a5b9b813ea2961282fb1ed2db6b71b553729b8` |
| Frozen complete synthetic banks | `c2fcd31f1b7b377d0deb917d199edeeb44ccafd5ab1929011290a4e27afdd733` |
| Executed diagnostic source | `8f69c4ad0159ebb1e095b1707cd91b93a40f01b64471ee303c8300b06c475973` |
| `aggregate.json` | `b0b15150b835e1b6d291429db286eb9f08b0ab4544a31fceccf0dc583b75cfcc` |

The aggregate retains per-leaf outcomes, domain and penalty projections, score
and coverage changes, fixed-reference orderings, normalization effects,
denominators and source identities. Private invocation metadata, receipts,
owner identifiers and absolute paths are excluded. This is a prospective public
package; preparation does not establish publication.
